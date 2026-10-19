"""Compiled template shapes: guards, per-node equivalence, teardown, and cache bounds."""

import gc
import weakref

import pytest
from conftest import StubNode, collect_texts

from wybthon import For, Fragment, Ref, create_signal, div, flush, h, span
from wybthon import _shapes as template
from wybthon.diagnostics import profile


def outer_html(node):
    """Serialize a stub node (elements, text, comments) for structural comparison."""
    if getattr(node, "_is_comment", False):
        return f"<!--{node.nodeValue}-->"
    if getattr(node, "_is_text", False):
        return f"[{node.nodeValue}]"
    attrs = "".join(f' {k}="{v}"' for k, v in sorted(node.attributes.items()))
    inner = "".join(outer_html(child) for child in node.childNodes)
    return f"<{node.tag}{attrs}>{inner}</{node.tag}>"


def test_repeated_templates_bind_each_instances_values_and_lifetimes(wyb, root_element):
    rows, set_rows = create_signal(list(range(20)))
    label, set_label = create_signal("first")
    refs, events = [], []

    def row(value, index):
        ref = Ref()
        refs.append(ref)
        return div(
            h("button", {"on_click": lambda e: events.append(value), "ref": ref}, str(value)),
            span(label),
            class_=lambda: "even" if value % 2 == 0 else "odd",
            data_row=value,
        )

    with profile() as measured:
        root = wyb["reconciler"].render(For(rows, row), root_element)
    assert measured.counts["template_recipe_hits"] >= 18
    for value, ref in enumerate(refs):
        button = ref.current.element
        assert button.childNodes[0].nodeValue == str(value)
        assert button.parentNode.attributes["data-row"] == str(value)
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


CHANGES = [
    lambda: div(span("x"), span("y"), class_="changed"),
    lambda: div(span("x"), span("y"), class_=lambda: "dynamic"),
    lambda: div(span("x"), span("y"), class_={"yes": True}),
    lambda: div(span("x"), span("y"), class_={"yes": lambda: True}),
    lambda: div(span("x"), span("y"), class_="base", id="added"),
    lambda: div(span("x"), span("y")),
    lambda: div(span("x"), h("strong", {}, "y"), class_="base"),
    lambda: div(span("x"), span("y"), span("z"), class_="base"),
    lambda: div(span("x"), class_="base"),
    lambda: div(span("x", "adjacent"), span("y"), class_="base"),
    lambda: div(span(None, False, 12), span(3.5), class_="base"),
    lambda: div(Fragment(span("x"), span("y")), class_="base"),
    lambda: div(span(lambda: "hole"), span("y"), class_="base"),
    lambda: div(h("svg", {}, h("circle", {"r": 2})), span("y"), class_="base"),
    lambda: div(span("x"), span("y"), class_="base", on_click=lambda e: None),
    lambda: div(span("other text"), span(7), class_="base"),
]


@pytest.mark.parametrize("change", CHANGES)
def test_shape_guards_reject_structural_changes_without_side_effects(wyb, root_element, change):
    for _ in range(3):
        wyb["reconciler"].render(div(span("x"), span("y"), class_="base"), root_element)
    shape = template._recent["div"]
    base_key, other_key = [], []
    template._shape_key(div(span("x"), span("y"), class_="base"), base_key)
    template._shape_key(change(), other_key)
    kernel = wyb["kernel"]
    kernel.commit()
    before = len(kernel._ops)
    same_shape = tuple(base_key) == tuple(other_key)
    accepted = shape.mount(change(), root_element.node_id, None)
    if accepted:
        assert same_shape
    else:
        # A rejection changes nothing; the caller normalizes the tree and
        # looks its shape up by key, so a raw tree with the same normalized
        # shape (here, dropped booleans) is accepted after normalization.
        assert len(kernel._ops) == before
        if same_shape:
            tree = change()
            template._shape_key(tree, [])
            assert shape.mount(tree, root_element.node_id, None)


@pytest.mark.parametrize("make", CHANGES)
def test_compiled_mounts_match_per_node_mounting(wyb, make):
    reconciler, kernel = wyb["reconciler"], wyb["kernel"]

    def html(enabled):
        kernel.html_templates = enabled
        container = wyb["dom"].Element(node=StubNode(tag="div"))
        root = reconciler.render(make(), container)
        out = outer_html(container.element)
        root.dispose()
        return out

    per_node = html(False)
    for _ in range(3):
        assert html(True) == per_node


def test_patched_template_subtrees_materialize_and_dispose(wyb, root_element):
    show_extra, set_show_extra = create_signal(False)
    clicks = []

    def view():
        return div(
            span("a", on_click=lambda: clicks.append("a")),
            span("b", class_=lambda: "on" if show_extra() else "off"),
            *([span("extra", on_click=lambda: clicks.append("extra"))] if show_extra() else []),
        )

    root = wyb["reconciler"].render(div(view), root_element)
    set_show_extra(True)
    flush()
    host = root_element.element.childNodes[0].childNodes[0]
    assert [collect_texts(child) for child in host.childNodes] == [["a"], ["b"], ["extra"]]
    assert host.childNodes[1].attributes["class"] == "on"
    for child in host.childNodes:
        wyb["kernel"]._backend.dispatch("click", child)
    assert clicks == ["a", "extra"]
    root.dispose()
    assert not wyb["events"]._handlers
    assert not wyb["_dom_props"]._bindings


def test_hole_text_anchors_are_written_in_place(wyb, root_element):
    count, set_count = create_signal(1)
    root = wyb["reconciler"].render(div(span(count), span("label")), root_element)
    first = root_element.element.childNodes[0].childNodes[0]
    assert [n.nodeValue for n in first.childNodes] == ["1"]
    set_count(2)
    flush()
    assert [n.nodeValue for n in first.childNodes] == ["2"]
    root.dispose()


def test_recipe_normalization_preserves_dynamic_child_ownership(wyb, root_element):
    root = None
    for value in range(4):
        if root is not None:
            root.dispose()
        root = wyb["reconciler"].render(
            div(h(Fragment, {"key": "owned"}, span(str(value))), span(lambda: "dynamic")), root_element
        )
        assert [text for text in collect_texts(root_element.element) if text.strip()] == [str(value), "dynamic"]
    root.dispose()


def test_shapes_are_bounded_and_dont_retain_instance_objects(wyb, root_element):
    class Callback:
        def __call__(self, event):
            pass

    callback = Callback()
    reference = weakref.ref(callback)
    for index in range(template._SHAPE_CACHE_MAX + 50):
        tree = div(h("button", {"on_click": callback}, "go"), span("body"), class_=f"recipe-{index}")
        wyb["reconciler"].render(tree, root_element).dispose()
    del tree, callback
    gc.collect()
    assert reference() is None
    assert len(template._shapes) <= template._SHAPE_CACHE_MAX
    assert len(template._recent) <= template._SHAPE_CACHE_MAX
    assert len(wyb["kernel"]._templates) <= wyb["kernel"]._TEMPLATE_LIMIT


def test_template_prop_names_are_data_and_never_generated_source(wyb, root_element):
    malicious = "x']; raise RuntimeError('interpolated'); #"
    for value in range(3):
        other = wyb["dom"].Element(node=StubNode(tag="div"))
        root = wyb["reconciler"].render(div(span("x"), span("y"), **{malicious: str(value)}), other)
        assert other.element.childNodes[0].attributes[malicious] == str(value)
        root.dispose()


def _table_sizes(wyb):
    return (
        sum(len(v) for v in wyb["events"]._handlers.values()),
        sum(len(v) for v in wyb["_dom_props"]._bindings.values()),
        wyb["kernel"].stats()["nodes"],
    )


def test_compiled_rows_teardown_releases_handlers_bindings_and_nodes(wyb, root_element):
    rows, set_rows = create_signal([])
    selected, set_selected = create_signal(0)
    clicks = []

    def row(value, index):
        return div(
            h("button", {"on_click": lambda: clicks.append(value)}, str(value)),
            span(lambda: f"#{index()}"),
            class_=lambda: "on" if selected() == value else "off",
        )

    root = wyb["reconciler"].render(div(For(rows, row)), root_element)
    baseline = _table_sizes(wyb)
    for _ in range(2):
        set_rows(list(range(25)))
        flush()
        handlers, _bindings, nodes = _table_sizes(wyb)
        # Compiled rows keep their reactive bindings on the row owner rather
        # than in the per-node table; handlers live in the per-node table.
        assert handlers == baseline[0] + 25
        assert nodes > baseline[2]
        set_selected(3)
        flush()
        buttons = [child.childNodes[0] for child in root_element.element.childNodes[0].childNodes if child.tag]
        wyb["kernel"]._backend.dispatch("click", buttons[3])
        assert clicks[-1] == 3
        set_rows([])
        flush()
        assert _table_sizes(wyb) == baseline
    root.dispose()
    assert not wyb["events"]._handlers
    assert wyb["kernel"].stats()["nodes"] <= 1


def test_component_template_unmount_returns_tables_to_baseline(wyb, root_element):
    from wybthon import Prop, Props, component

    show, set_show = create_signal(False)
    count, set_count = create_signal(0)

    class CardProps(Props):
        title: Prop[str]

    @component
    def Card(props: CardProps):
        return div(
            h("h2", {}, props.title),
            h("button", {"on_click": lambda: set_count(lambda n: n + 1)}, "+"),
            span(t"count {count}"),
            class_=t"card {count}",
        )

    root = wyb["reconciler"].render(div(lambda: Card(title="T") if show() else None), root_element)
    baseline = _table_sizes(wyb)
    for _ in range(3):
        set_show(True)
        flush()
        assert _table_sizes(wyb) != baseline
        set_count(lambda n: n + 1)
        flush()
        set_show(False)
        flush()
        assert _table_sizes(wyb) == baseline
    root.dispose()
    assert not wyb["events"]._handlers


def test_bulk_replace_emits_one_dispose_range(wyb, root_element, monkeypatch):
    kernel = wyb["kernel"]
    rows, set_rows = create_signal([{"id": i} for i in range(100)])
    disposed = []

    def row(item, index):
        from wybthon import on_cleanup

        on_cleanup(lambda: disposed.append(item["id"]))
        return div(span(str(item["id"])), span("x"))

    root = wyb["reconciler"].render(div(For(rows, row)), root_element)
    nodes_before = kernel.stats()["nodes"]
    recorded = []
    original = kernel._backend.apply
    monkeypatch.setattr(kernel._backend, "apply", lambda ops: (recorded.extend(ops), original(ops)))
    set_rows([{"id": i} for i in range(100, 200)])
    flush()
    codes = [op[0] for op in recorded]
    assert codes.count(kernel.OP_DISPOSE_RANGE) == 1
    assert codes.count(kernel.OP_CLONE) == 100
    assert kernel.OP_REMOVE not in codes and kernel.OP_DISPOSE not in codes and kernel.OP_RELEASE not in codes
    assert sorted(disposed) == list(range(100))
    assert kernel.stats()["nodes"] == nodes_before
    texts = [t for t in collect_texts(root_element.element) if t.strip() and t != "x"]
    assert texts == [str(i) for i in range(100, 200)]
    recorded.clear()
    set_rows([])
    flush()
    assert [op[0] for op in recorded].count(kernel.OP_DISPOSE_RANGE) == 1
    root.dispose()
