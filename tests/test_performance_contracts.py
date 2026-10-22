"""Compatibility at the boundaries of compact storage and list fast paths."""

import asyncio
import gc
import weakref

import pytest
from conftest import StubNode, collect_texts

from wybthon import (
    For,
    Ref,
    action,
    create_memo,
    create_projection,
    create_signal,
    create_store,
    deep,
    flush,
    html,
    map_array,
    on_cleanup,
)
from wybthon._vector import Vector
from wybthon.diagnostics import profile
from wybthon.kernel import OP_CLONE
from wybthon.store import DraftExpiredError


@pytest.mark.parametrize("size", [0, 1, 31, 32, 33, 1023, 1024, 1025, 32768, 32769])
def test_bulk_vectors_preserve_values_across_tree_boundaries(size):
    values = list(range(size))
    vector = Vector(iter(values))
    assert list(vector) == values
    assert list(vector.append("tail")) == [*values, "tail"]
    assert vector[::-17] == values[::-17]
    if size:
        assert list(vector.pop()) == values[:-1]
        assert list(vector.set(-1, "last")) == [*values[:-1], "last"]
    for start in sorted({0, min(1, size), min(32, size), min(1024, size), size}):
        trimmed = vector.splice(start, size - start, ())
        assert list(trimmed) == values[:start]
        assert list(trimmed.append("next")) == [*values[:start], "next"]
        assert list(vector) == values
    middle = size // 2
    assert list(vector.splice(middle, min(3, size - middle), iter(["a", "b"]))) == (
        values[:middle] + ["a", "b"] + values[middle + min(3, size - middle) :]
    )


def test_shared_store_entities_notify_each_remaining_parent(wyb):
    store, write = create_store({"entity": {"n": 0}, "left": [], "right": []})

    def share(d):
        d.left.extend([d.entity, d.entity])
        d.right.append(d.entity)

    write(share)
    flush()
    calls = {"left": 0, "right": 0}

    def read(side):
        calls[side] += 1
        return deep(store[side])

    left = create_memo(lambda: read("left"))
    right = create_memo(lambda: read("right"))
    assert left() == [{"n": 0}, {"n": 0}]
    assert right() == [{"n": 0}]
    write(lambda d: (d.left.pop(), None)[1])
    flush()
    assert left() == [{"n": 0}]
    write(lambda d: setattr(d.entity, "n", 1))
    flush()
    assert left() == right() == [{"n": 1}]
    write(lambda d: d.left.clear())
    flush()
    assert left() == []
    before = calls.copy()
    write(lambda d: setattr(d.entity, "n", 2))
    flush()
    assert left() == []
    assert right() == [{"n": 2}]
    assert calls == {"left": before["left"], "right": before["right"] + 1}
    assert store.right[0] is store.entity


def test_repeated_links_to_one_parent_keep_deep_subscription(wyb):
    store, write = create_store([{"n": 0}])
    write(lambda d: d.append(d[0]))
    flush()
    memo = create_memo(lambda: deep(store))
    assert memo() == [{"n": 0}, {"n": 0}]
    write(lambda d: (d.pop(), None)[1])
    flush()
    assert memo() == [{"n": 0}]
    write(lambda d: setattr(d[0], "n", 1))
    flush()
    assert memo() == [{"n": 1}]


@pytest.mark.parametrize("shared", [False, True])
def test_retained_entity_doesnt_retain_its_parents(wyb, shared):
    store, write = create_store({"entity": {"n": 0}, "other": []})
    entity = store.entity
    if shared:
        write(lambda d: d.other.append(d.entity))
        flush()
    parent = weakref.ref(store._node)
    other = weakref.ref(store.other._node)
    del store, write
    gc.collect()
    assert parent() is None and other() is None
    assert entity.n == 0


def test_map_array_prefix_keys_run_once_and_replacements_stay_reactive(wyb):
    source, write = create_signal([{"id": 1, "v": "a"}, {"id": 2, "v": "b"}])
    keys, disposed = [], []

    def key(item):
        keys.append(item["id"])
        return item["id"]

    def row(item, index):
        identity = item.peek()["id"]
        on_cleanup(lambda: disposed.append(identity))
        return create_memo(lambda: (item()["v"], index()))

    mapped = map_array(source, row, keyed=key)
    first, second = mapped()
    assert (first(), second()) == (("a", 0), ("b", 1))
    keys.clear()
    write([{"id": 1, "v": "new"}, {"id": 3, "v": "c"}, {"id": 2, "v": "b"}])
    flush()
    assert keys == [1, 3, 2]
    assert mapped()[0] is first and mapped()[2] is second
    assert (first(), second()) == (("new", 0), ("b", 2))
    assert disposed == []
    mapped.dispose()
    assert sorted(disposed) == [1, 2, 3]


def test_map_array_append_truncate_and_duplicate_occurrence_identity(wyb):
    source, write = create_signal([1, 1, 2])
    disposed = []

    def row(item, index):
        token = object()
        on_cleanup(lambda: disposed.append(token))
        return token, index

    mapped = map_array(source, row, fallback=lambda: "empty")
    first, second, third = mapped()
    write([1, 2, 1, 3])
    flush()
    assert mapped()[:3] == [first, third, second]
    assert [entry[1]() for entry in mapped()] == [0, 1, 2, 3]
    write([1, 2])
    flush()
    assert mapped() == [first, third]
    assert second[0] in disposed and first[0] not in disposed
    write([])
    flush()
    assert mapped() == ["empty"]
    mapped.dispose()


def test_draft_clear_batches_disposal_and_preserves_transaction_boundaries(wyb, root_element):
    store, write = create_store(list(range(1000)))
    disposed = []

    def row(item, index):
        on_cleanup(lambda: disposed.append(item))
        return html(t"<span>{item}</span>")

    root = wyb["reconciler"].render(html(t"{For(store, row)}"), root_element)
    escaped = []

    def clear(draft):
        escaped.append(draft)
        draft.clear()
        assert len(draft) == 0
        assert len(store) == 1000

    with profile() as measured:
        write(clear)
        assert disposed == []
        flush()
    assert len(store) == 0
    assert disposed == list(reversed(range(1000)))
    assert measured.counts["list_edits"] == 1
    assert measured.counts["commits"] == 1
    with pytest.raises(DraftExpiredError):
        escaped[0].clear()
    write(lambda draft: (draft.clear(), draft.append(42)) and None)
    flush()
    assert list(store) == [42]

    def abort(draft):
        draft.clear()
        raise ValueError("abort")

    with pytest.raises(ValueError, match="abort"):
        write(abort)
    flush()
    assert list(store) == [42]
    root.dispose()


def test_draft_clear_and_refill_retains_cleanup_order_through_a_transition(wyb, root_element):
    async def main():
        store, write = create_store([1, 2, 3])
        created, disposed = [], []

        def row(item, index):
            created.append(item)
            on_cleanup(lambda: disposed.append(item))
            return html(t"<span>{item}</span>")

        root = wyb["reconciler"].render(html(t"{For(store, row)}"), root_element)
        gate = asyncio.Event()

        @action
        async def replace():
            write(lambda draft: (draft.clear(), draft.extend([1, 2, 3])) and None)
            await gate.wait()

        future = replace()
        flush()
        assert list(store) == [1, 2, 3]
        assert disposed == [] and created == [1, 2, 3]
        gate.set()
        await future
        flush()
        assert disposed == [3, 2, 1]
        assert created == [1, 2, 3, 1, 2, 3]
        assert list(store) == [1, 2, 3]
        root.dispose()

    asyncio.run(main())


# ---------------------------------------------------------------------------
# Template rows: one kernel command per row, native teardown, bounded tables
# ---------------------------------------------------------------------------


def _texts(node):
    return [text for text in collect_texts(node) if text.strip()]


def _table_sizes(wyb):
    events = wyb["events"]
    return (
        sum(len(tuple(events.handlers_of(entry))) for entry in events._handlers.values()),
        sum(len(v) for v in wyb["_dom_props"]._bindings.values()),
        wyb["kernel"].stats()["nodes"],
    )


def _outer_html(node):
    """Serialize a stub node's elements and text for structural comparison.

    Comment markers and empty text nodes (hole anchors) are left out, and
    adjacent text is joined: they're placement details, not content.
    """
    if getattr(node, "_is_text", False):
        return node.nodeValue
    if getattr(node, "_is_comment", False):
        return ""
    attrs = "".join(f' {k}="{v}"' for k, v in sorted(node.attributes.items()))
    inner = "".join(_outer_html(child) for child in node.childNodes)
    return f"<{node.tag}{attrs}>{inner}</{node.tag}>"


def test_template_rows_bind_each_instances_values_and_lifetimes(wyb, root_element):
    rows, set_rows = create_signal(list(range(20)))
    label, set_label = create_signal("first")
    refs, events = [], []

    def row(value, index):
        ref = Ref()
        refs.append(ref)

        def click(e):
            events.append(value)

        return html(t"""
          <div class={"even" if value % 2 == 0 else "odd"} data-row={value}>
            <button onclick={click} ref={ref}>{value}</button><span>{label}</span>
          </div>
        """)

    with profile() as measured:
        root = wyb["reconciler"].render(html(t"{For(rows, row)}"), root_element)
    # One fused clone command per row.
    assert measured.counts["template_clones"] == 20
    assert measured.counts[f"op_{OP_CLONE}"] == 20
    for value, ref in enumerate(refs):
        button = ref.current.element
        assert button.childNodes[0].nodeValue == str(value)
        assert button.parentNode.attributes["data-row"] == str(value)
        assert button.parentNode.attributes["class"] == ("even" if value % 2 == 0 else "odd")
        wyb["kernel"]._backend.dispatch("click", button)
    assert events == list(range(20))
    set_label("second")
    flush()
    assert collect_texts(root_element.element).count("second") == 20
    set_rows([])
    flush()
    assert all(ref.current is None for ref in refs)
    assert not wyb["events"]._handlers
    root.dispose()
    assert wyb["kernel"].stats()["nodes"] <= 1


def test_appending_template_rows_is_one_command_per_row(wyb, root_element):
    rows, set_rows = create_signal([{"id": i, "label": f"row {i}"} for i in range(10)])
    selected, set_selected = create_signal(None)
    is_selected = create_projection(lambda: {} if selected() is None else {selected(): True})

    def row(item, index):
        def select():
            set_selected(item["id"])

        return html(t"""
          <tr class={"danger" if is_selected.get(item["id"]) else ""}>
            <td>{item["id"]}</td><td><a onclick={select}>{item["label"]}</a></td>
          </tr>
        """)

    root = wyb["reconciler"].render(html(t"<table><tbody>{For(rows, row)}</tbody></table>"), root_element)
    with profile() as measured:
        set_rows([*rows(), *({"id": i, "label": f"row {i}"} for i in range(10, 110))])
        flush()
    assert measured.counts["rows_created"] == 100
    assert measured.counts["template_clones"] == 100
    assert measured.counts["commits"] == 1
    assert measured.counts["dom_ops"] <= 101
    with profile() as selection:
        set_selected(50)
        flush()
    assert selection.counts["rows_created"] == 0
    assert selection.counts["dom_ops"] == 1
    with profile() as selection:
        set_selected(60)
        flush()
    # One row loses the class, one gains it.
    assert selection.counts["dom_ops"] == 2
    tbody = root_element.element.childNodes[0].childNodes[0]
    assert [tr.attributes.get("class") for tr in tbody.childNodes if tr.tag][60] == "danger"
    root.dispose()


def test_template_rows_teardown_releases_handlers_bindings_and_nodes(wyb, root_element):
    rows, set_rows = create_signal([])
    selected, set_selected = create_signal(0)
    clicks = []

    def row(value, index):
        def click():
            clicks.append(value)

        return html(t"""
          <div class={"on" if selected() == value else "off"}>
            <button onclick={click}>{value}</button><span>#{index()}</span>
          </div>
        """)

    root = wyb["reconciler"].render(html(t"<div>{For(rows, row)}</div>"), root_element)
    baseline = _table_sizes(wyb)
    for _ in range(2):
        set_rows(list(range(25)))
        flush()
        handlers, _bindings, nodes = _table_sizes(wyb)
        # Template rows keep their reactive bindings on the row owner rather
        # than in the per-node table; handlers live in the per-node table.
        assert handlers == baseline[0] + 25
        assert nodes > baseline[2]
        set_selected(3)
        flush()
        host = root_element.element.childNodes[0]
        divs = [child for child in host.childNodes if child.tag]
        assert divs[3].attributes["class"] == "on"
        buttons = [child.childNodes[0] for child in divs]
        wyb["kernel"]._backend.dispatch("click", buttons[3])
        assert clicks[-1] == 3
        set_rows([])
        flush()
        assert _table_sizes(wyb) == baseline
    root.dispose()
    assert not wyb["events"]._handlers
    assert wyb["kernel"].stats()["nodes"] <= 1


def test_component_template_unmount_returns_tables_to_baseline(wyb, root_element):
    from wybthon import Props, component

    show, set_show = create_signal(False)
    count, set_count = create_signal(0)

    class CardProps(Props):
        title: str

    @component
    def Card(props: CardProps):
        def increment():
            set_count(lambda n: n + 1)

        return html(t"""
          <div class="card {count()}">
            <h2>{props.title}</h2><button onclick={increment}>+</button><span>count {count()}</span>
          </div>
        """)

    root = wyb["reconciler"].render(html(t"<div>{Card(title='T') if show() else None}</div>"), root_element)
    baseline = _table_sizes(wyb)
    for _ in range(3):
        set_show(True)
        flush()
        assert _table_sizes(wyb) != baseline
        assert "T" in _texts(root_element.element)
        set_count(lambda n: n + 1)
        flush()
        set_show(False)
        flush()
        assert _table_sizes(wyb) == baseline
    root.dispose()
    assert not wyb["events"]._handlers


def test_bulk_replace_of_template_rows_emits_one_dispose_range(wyb, root_element, monkeypatch):
    kernel = wyb["kernel"]
    rows, set_rows = create_signal([{"id": i} for i in range(100)])
    disposed = []

    def row(item, index):
        on_cleanup(lambda: disposed.append(item["id"]))
        return html(t"<div><span>{item['id']}</span><span>x</span></div>")

    root = wyb["reconciler"].render(html(t"<div>{For(rows, row)}</div>"), root_element)
    nodes_before = kernel.stats()["nodes"]
    recorded = []
    original = kernel._backend.apply
    monkeypatch.setattr(kernel._backend, "apply", lambda ops: (recorded.extend(ops), original(ops)))
    set_rows([{"id": i} for i in range(100, 200)])
    flush()
    codes = [op[0] for op in recorded]
    assert codes.count(kernel.OP_DISPOSE_RANGE) == 1
    # One clone per new row, and nothing else per row.
    assert codes.count(kernel.OP_CLONE) == 100
    assert len(codes) == 101
    assert sorted(disposed) == list(range(100))
    assert kernel.stats()["nodes"] == nodes_before
    texts = [t for t in _texts(root_element.element) if t != "x"]
    assert texts == [str(i) for i in range(100, 200)]
    recorded.clear()
    set_rows([])
    flush()
    assert [op[0] for op in recorded] == [kernel.OP_DISPOSE_RANGE]
    root.dispose()


def test_hole_text_anchors_are_written_in_place(wyb, root_element):
    count, set_count = create_signal(1)
    root = wyb["reconciler"].render(html(t"<div><span>{count}</span><span>label</span></div>"), root_element)
    first = root_element.element.childNodes[0].childNodes[0]
    assert [n.nodeValue for n in first.childNodes] == ["1"]
    set_count(2)
    flush()
    assert [n.nodeValue for n in first.childNodes] == ["2"]
    root.dispose()


def test_patched_template_instances_update_and_dispose(wyb, root_element):
    show_extra, set_show_extra = create_signal(False)
    clicks = []

    def on_a():
        clicks.append("a")

    def on_extra():
        clicks.append("extra")

    def view():
        extra = html(t"<span onclick={on_extra}>extra</span>") if show_extra() else None
        return html(
            t"""<div><span onclick={on_a}>a</span><span class={"on" if show_extra() else "off"}>b</span>{extra}</div>"""
        )

    # `_dom_props` isn't reloaded per test, so compare against the tables as they were.
    baseline = _table_sizes(wyb)[:2]
    root = wyb["reconciler"].render(html(t"<div>{view()}</div>"), root_element)
    set_show_extra(True)
    flush()
    host = root_element.element.childNodes[0].childNodes[0]
    assert [collect_texts(child) for child in host.childNodes if child.tag] == [["a"], ["b"], ["extra"]]
    assert host.childNodes[1].attributes["class"] == "on"
    for child in host.childNodes:
        if child.tag:
            wyb["kernel"]._backend.dispatch("click", child)
    assert clicks == ["a", "extra"]
    root.dispose()
    assert not wyb["events"]._handlers
    assert _table_sizes(wyb)[:2] == baseline


def test_template_registry_is_bounded_and_doesnt_retain_instance_objects(wyb, root_element):
    class Callback:
        def __call__(self, event):
            pass

    callback = Callback()
    reference = weakref.ref(callback)
    kernel = wyb["kernel"]
    for index in range(kernel._TEMPLATE_LIMIT + 50):
        tree = html(t'<div class="recipe-{index}"><button onclick={callback}>go</button><span>body</span></div>')
        wyb["reconciler"].render(tree, root_element).dispose()
    del tree, callback
    gc.collect()
    assert reference() is None
    assert len(kernel._templates) <= kernel._TEMPLATE_LIMIT
    assert not wyb["events"]._handlers


def test_spread_prop_names_are_data_and_never_generated_source(wyb, root_element):
    malicious = "x']; raise RuntimeError('interpolated'); #"
    for value in range(3):
        other = wyb["dom"].Element(node=StubNode(tag="div"))
        attrs = {malicious: str(value)}
        root = wyb["reconciler"].render(html(t"<div {attrs}><span>x</span><span>y</span></div>"), other)
        assert other.element.childNodes[0].attributes[malicious] == str(value)
        root.dispose()


_flag, _set_flag = create_signal(True)


def _noop(event):
    pass


VARIANTS = [
    lambda: html(t'<div class="changed"><span>x</span><span>y</span></div>'),
    lambda: html(t"<div class={_flag() and 'dynamic'}><span>x</span><span>y</span></div>"),
    lambda: html(t"<div class={ {'yes': True} }><span>x</span><span>y</span></div>"),
    lambda: html(t"<div class={ {'yes': _flag} }><span>x</span><span>y</span></div>"),
    lambda: html(t'<div class="base" id="added"><span>x</span><span>y</span></div>'),
    lambda: html(t'<div class="base"><span>x</span><strong>y</strong></div>'),
    lambda: html(t'<div class="base"><span>x adjacent</span><span>{"y"} {"z"}</span></div>'),
    lambda: html(t'<div class="base"><span>{None}{False}{12}</span><span>{3.5}</span></div>'),
    lambda: html(t'<div class="base">{html(t"<span>x</span><span>y</span>")}</div>'),
    lambda: html(t'<div class="base"><span>{_flag() and "hole"}</span><span>y</span></div>'),
    lambda: html(t'<div class="base"><svg><circle r="2"></circle></svg><span>y</span></div>'),
    lambda: html(t'<div class="base" onclick={_noop}><span>x</span><span>y</span></div>'),
    lambda: html(t'<div class="base">{[html(t"<i>{n}</i>") for n in range(3)]}</div>'),
]


@pytest.mark.parametrize("make", VARIANTS)
def test_native_template_mounts_match_per_node_mounting(wyb, make):
    reconciler, kernel = wyb["reconciler"], wyb["kernel"]

    def mount(enabled):
        kernel.html_templates = enabled
        container = wyb["dom"].Element(node=StubNode(tag="div"))
        root = reconciler.render(make(), container)
        out = _outer_html(container.element)
        root.dispose()
        return out

    per_node = mount(False)
    for _ in range(3):
        assert mount(True) == per_node
