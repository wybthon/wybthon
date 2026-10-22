"""Control flow: Show, For, Repeat, Switch/Match, dynamic, NoHydration/Hydration, client_only."""

import asyncio
from collections.abc import Callable
from typing import Any

from conftest import StubNode

from wybthon import _warnings, html
from wybthon.component import component
from wybthon.flow import (
    For,
    Hydration,
    Match,
    NoHydration,
    Repeat,
    Show,
    Switch,
    client_only,
    dynamic,
    is_hydrating,
    on_hydration_end,
)
from wybthon.reactivity import Props, create_signal, flush, on_cleanup, untrack


def texts(node: StubNode) -> list[str]:
    """Visible text: skips comment markers and whitespace-only placeholders."""
    if getattr(node, "_is_comment", False):
        return []
    out = [node.nodeValue] if node._is_text and node.nodeValue and node.nodeValue.strip() else []
    for child in node.childNodes:
        out.extend(texts(child))
    return out


class RowProps(Props):
    item: dict


class LabelProps(Props):
    label: str


def elements(node: StubNode) -> list[StubNode]:
    return [n for n in node.childNodes if n.tag]


# ---------------------------------------------------------------------------
# Show
# ---------------------------------------------------------------------------


def test_show_toggles_children_and_fallback(wyb, root_element):
    on, set_on = create_signal(False)
    view = html(t"<div>{Show(on, lambda: html(t'<p>yes</p>'), fallback=lambda: html(t'<p>no</p>'))}</div>")
    wyb["reconciler"].render(view, root_element)
    assert texts(root_element.element) == ["no"]
    set_on(True)
    flush()
    assert texts(root_element.element) == ["yes"]
    set_on(False)
    flush()
    assert texts(root_element.element) == ["no"]


def test_show_accepts_static_vnode_children(wyb, root_element):
    on, set_on = create_signal(True)
    wyb["reconciler"].render(html(t"<div>{Show(on, html(t'<p>static</p>'))}</div>"), root_element)
    assert texts(root_element.element) == ["static"]
    set_on(False)
    flush()
    assert texts(root_element.element) == []


def test_show_callback_receives_accessor_and_is_not_recreated(wyb, root_element):
    user, set_user = create_signal(None)
    created: list[int] = []

    def body(u):
        created.append(1)
        return html(t"<p>hi {u()['name']}</p>")

    wyb["reconciler"].render(html(t"<div>{Show(user, body)}</div>"), root_element)
    assert texts(root_element.element) == []
    set_user({"name": "Ada"})
    flush()
    assert texts(root_element.element) == ["hi ", "Ada"]
    set_user({"name": "Grace"})
    flush()
    assert texts(root_element.element) == ["hi ", "Grace"]
    assert created == [1]


def test_show_keyed_passes_raw_value_and_recreates_on_change(wyb, root_element):
    user, set_user = create_signal({"name": "Ada"})
    created: list[str] = []

    def body(u):
        created.append(u["name"])
        return html(t"<p>{u['name']}</p>")

    wyb["reconciler"].render(html(t"<div>{Show(user, body, keyed=True)}</div>"), root_element)
    set_user({"name": "Grace"})
    flush()
    assert texts(root_element.element) == ["Grace"]
    assert created == ["Ada", "Grace"]


def test_show_disposes_children_scope_when_hidden(wyb, root_element):
    on, set_on = create_signal(True)
    log: list[str] = []

    @component
    def Child():
        on_cleanup(lambda: log.append("cleanup"))
        return html(t"<p>c</p>")

    wyb["reconciler"].render(html(t"<div>{Show(on, lambda: Child())}</div>"), root_element)
    set_on(False)
    flush()
    assert log == ["cleanup"]


def test_show_does_not_rerender_on_truthy_to_truthy_change(wyb, root_element):
    count, set_count = create_signal(1)
    renders: list[int] = []

    def body():
        renders.append(1)
        return html(t"<p>on</p>")

    wyb["reconciler"].render(html(t"<div>{Show(count, body)}</div>"), root_element)
    set_count(2)
    flush()
    assert renders == [1]


def test_show_condition_expression_in_a_template_is_reactive(wyb, root_element):
    # `count() > 2` is dynamic, so the compiler passes `Show` a getter.
    count, set_count = create_signal(1)
    renders: list[int] = []

    def big():
        renders.append(1)
        return html(t"<b>big</b>")

    view = html(t"<div>{Show(count() > 2, big, html(t'<i>small</i>'))}</div>")
    wyb["reconciler"].render(view, root_element)
    assert texts(root_element.element) == ["small"]
    set_count(3)
    flush()
    assert texts(root_element.element) == ["big"]
    # Truthy to truthy keeps the branch.
    set_count(4)
    flush()
    assert texts(root_element.element) == ["big"]
    assert renders == [1]
    set_count(0)
    flush()
    assert texts(root_element.element) == ["small"]


def test_show_callback_from_a_getter_receives_the_value_accessor(wyb, root_element):
    # A dynamic `when` is a getter; the branch callback still gets an
    # accessor that follows the current value.
    user, set_user = create_signal({"name": "Ada"})
    view = html(t"<div>{Show(user()['name'], lambda name: html(t'<p>{name()}</p>'))}</div>")
    wyb["reconciler"].render(view, root_element)
    assert texts(root_element.element) == ["Ada"]
    set_user({"name": "Grace"})
    flush()
    assert texts(root_element.element) == ["Grace"]


# ---------------------------------------------------------------------------
# For
# ---------------------------------------------------------------------------


def _items(*ids: int) -> list[dict]:
    return [{"id": i, "t": f"t{i}"} for i in ids]


def test_for_renders_rows_and_fallback(wyb, root_element):
    items, set_items = create_signal([])
    view = html(
        t"<ul>{For(items, lambda item, i: html(t'<li>{item["t"]}</li>'), fallback=html(t'<li>empty</li>'))}</ul>"
    )
    wyb["reconciler"].render(view, root_element)
    assert texts(root_element.element) == ["empty"]
    set_items(_items(1, 2))
    flush()
    assert texts(root_element.element) == ["t1", "t2"]
    set_items([])
    flush()
    assert texts(root_element.element) == ["empty"]


def test_for_keyed_by_identity_moves_rows_and_updates_index(wyb, root_element):
    a, b, c = _items(1, 2, 3)
    items, set_items = create_signal([a, b])
    created: list[int] = []

    def row(item, index):
        created.append(item["id"])
        return html(t"<li>{index()}:{item['t']}</li>")

    wyb["reconciler"].render(html(t"<ul>{For(items, row)}</ul>"), root_element)
    assert texts(root_element.element) == ["0", ":", "t1", "1", ":", "t2"]
    ul_node = elements(root_element.element)[0]
    before = {id(n) for n in elements(ul_node)}
    set_items([b, c, a])
    flush()
    assert texts(root_element.element) == ["0", ":", "t2", "1", ":", "t3", "2", ":", "t1"]
    assert created == [1, 2, 3]
    after = {id(n) for n in elements(ul_node)}
    assert before <= after


def test_for_index_is_the_row_accessor(wyb, root_element):
    # With the default keyed matching the index argument is an accessor
    # (the row itself), not a `Signal`; reading it is tracked.
    a, b = _items(1, 2)
    items, set_items = create_signal([a, b])
    seen: list[Any] = []

    def row(item, index):
        seen.append(index)
        return html(t"<li>{(lambda: f'{index()}={item["id"]}')}</li>")

    wyb["reconciler"].render(html(t"<ul>{For(items, row)}</ul>"), root_element)
    assert all(callable(i) for i in seen)
    assert [i() for i in seen] == [0, 1]
    set_items([b, a])
    flush()
    assert texts(root_element.element) == ["0=2", "1=1"]
    assert [untrack(i) for i in seen] == [1, 0]


def test_for_rows_are_disposed_when_removed(wyb, root_element):
    a, b = _items(1, 2)
    items, set_items = create_signal([a, b])
    disposed: list[int] = []

    def row(item, index):
        on_cleanup(lambda: disposed.append(item["id"]))
        return html(t"<li>{item['t']}</li>")

    wyb["reconciler"].render(html(t"<ul>{For(items, row)}</ul>"), root_element)
    set_items([b])
    flush()
    assert disposed == [1]
    assert texts(root_element.element) == ["t2"]


def test_for_unkeyed_reuses_rows_by_position(wyb, root_element):
    items, set_items = create_signal(["a", "b"])
    created: list[int] = []

    def row(item, index):
        created.append(index)
        return html(t"<li>{(lambda: f'{index}:{item()}')}</li>")

    wyb["reconciler"].render(html(t"<ul>{For(items, row, keyed=False)}</ul>"), root_element)
    assert texts(root_element.element) == ["0:a", "1:b"]
    set_items(["x", "y", "z"])
    flush()
    assert texts(root_element.element) == ["0:x", "1:y", "2:z"]
    assert created == [0, 1, 2]


def test_for_keyed_by_function(wyb, root_element):
    items, set_items = create_signal(_items(1))
    created: list[int] = []

    def row(item, index):
        created.append(item()["id"])
        return html(t"<li>{(lambda: f'{index()}:{item()["t"]}')}</li>")

    wyb["reconciler"].render(html(t"<ul>{For(items, row, keyed=lambda x: x['id'])}</ul>"), root_element)
    set_items([{"id": 2, "t": "new"}, {"id": 1, "t": "T1"}])
    flush()
    assert texts(root_element.element) == ["0:new", "1:T1"]
    assert created == [1, 2]


def test_for_with_plain_list_warns_once(wyb, root_element, capsys):
    _warnings._reset_warning_dedupe()
    rows = ["a", "b"]
    wyb["reconciler"].render(html(t"<ul>{For(rows, lambda item, i: html(t'<li>{item}</li>'))}</ul>"), root_element)
    assert texts(root_element.element) == ["a", "b"]
    assert "plain list" in capsys.readouterr().err


def test_for_rows_are_isolated_scopes(wyb, root_element):
    items, _ = create_signal(_items(1, 2))
    hits, set_hits = create_signal({1: 0, 2: 0})
    renders: list[int] = []

    def label(iid: int) -> str:
        renders.append(iid)
        return str(hits()[iid])

    def row(item, index):
        return html(t"<li>{label(item['id'])}</li>")

    wyb["reconciler"].render(html(t"<ul>{For(items, row)}</ul>"), root_element)
    set_hits({1: 1, 2: 0})
    flush()
    # Both holes read `hits`, so both re-render; the rows themselves are not
    # recreated (no extra row creation, only hole updates).
    assert texts(root_element.element) == ["1", "0"]
    assert renders.count(1) == 2 and renders.count(2) == 2


def test_for_source_expression_in_a_template_updates(wyb, root_element):
    # `items()` is dynamic, so `For` receives a getter for the list.
    items, set_items = create_signal(["a", "b"])
    created: list[str] = []

    def row(item, index):
        created.append(item)
        return html(t"<li>{item}</li>")

    wyb["reconciler"].render(html(t"<ul>{For(items(), row)}</ul>"), root_element)
    assert texts(root_element.element) == ["a", "b"]
    set_items(["b", "c", "a"])
    flush()
    assert texts(root_element.element) == ["b", "c", "a"]
    assert created == ["a", "b", "c"]


def test_for_filtered_source_expression_updates(wyb, root_element):
    items, set_items = create_signal([1, 2, 3, 4])
    wyb["reconciler"].render(
        html(t"<ul>{For([n for n in items() if n % 2 == 0], lambda n, i: html(t'<li>{n}</li>'))}</ul>"), root_element
    )
    assert texts(root_element.element) == ["2", "4"]
    set_items([4, 5, 6])
    flush()
    assert texts(root_element.element) == ["4", "6"]


def test_for_callback_from_a_call_is_unwrapped_once(wyb, root_element):
    # `make_row(kind)` is a call, so the compiler passes `For` a getter; the
    # built-in evaluates it once, untracked, and uses the row function.
    rows, set_rows = create_signal(["a", "b"])
    kind, set_kind = create_signal("x")
    factories: list[str] = []

    def make_row(k: Callable[[], str]) -> Callable[[str, Any], Any]:
        factories.append(k())

        def row(item: str, index: Any) -> Any:
            return html(t"<li>{k()}-{item}</li>")

        return row

    wyb["reconciler"].render(html(t"<ul>{For(rows(), make_row(kind))}</ul>"), root_element)
    assert texts(root_element.element) == ["x", "-", "a", "x", "-", "b"]
    set_kind("y")
    flush()
    # The factory isn't re-run (its read was untracked); the rows' own holes update.
    assert factories == ["x"]
    assert texts(root_element.element) == ["y", "-", "a", "y", "-", "b"]
    set_rows(["c"])
    flush()
    assert texts(root_element.element) == ["y", "-", "c"]
    assert factories == ["x"]


def test_for_inserted_rows_mount_in_document_order(wyb, root_element):
    from wybthon.reactivity import on_settled

    one = _items(1)
    items, set_items = create_signal(one)
    order: list[int] = []

    @component
    def Row(props: RowProps):
        iid = untrack(lambda: props.item)["id"]
        on_settled(lambda: order.append(iid))
        return html(t"<li>{str(iid)}</li>")

    wyb["reconciler"].render(html(t"<ul>{For(items, lambda item, index: Row(item=item))}</ul>"), root_element)
    assert order == [1]
    # A run of appended siblings mounts front to back, so component bodies
    # and on_settled run in DOM order.
    set_items(one + _items(2, 3, 4))
    flush()
    assert order == [1, 2, 3, 4]
    # The same holds for a run inserted in the middle.
    set_items(one + _items(5, 6) + items()[1:])
    flush()
    assert order == [1, 2, 3, 4, 5, 6]
    assert texts(root_element.element) == ["1", "5", "6", "2", "3", "4"]


def test_for_never_patches_a_new_row_into_a_removed_one(wyb, root_element):
    items, set_items = create_signal(_items(1))
    bodies: list[int] = []

    @component
    def Row(props: RowProps):
        iid = untrack(lambda: props.item)["id"]
        bodies.append(iid)
        return html(t"<li>{str(iid)}</li>")

    wyb["reconciler"].render(html(t"<ul>{For(items, lambda item, index: Row(item=item))}</ul>"), root_element)
    # A new dict at the same position is a different item: the old row is
    # disposed and a fresh component mounts (never a props patch into the
    # disposed one).
    set_items([{"id": 1, "t": "changed"}])
    flush()
    assert bodies == [1, 1]
    assert texts(root_element.element) == ["1"]


# ---------------------------------------------------------------------------
# Repeat
# ---------------------------------------------------------------------------


def test_repeat_grows_and_shrinks(wyb, root_element):
    n, set_n = create_signal(2)
    created: list[int] = []

    def row(i: int):
        created.append(i)
        return html(t"<span>{str(i)}</span>")

    wyb["reconciler"].render(html(t"<div>{Repeat(n, row)}</div>"), root_element)
    assert texts(root_element.element) == ["0", "1"]
    set_n(4)
    flush()
    assert texts(root_element.element) == ["0", "1", "2", "3"]
    set_n(1)
    flush()
    assert texts(root_element.element) == ["0"]
    assert created == [0, 1, 2, 3]


def test_repeat_with_start_and_fallback(wyb, root_element):
    n, set_n = create_signal(0)
    view = html(
        t"<div>{Repeat(n, lambda i: html(t'<span>{i}</span>'), fallback=html(t'<span>none</span>'), start=5)}</div>"
    )
    wyb["reconciler"].render(view, root_element)
    assert texts(root_element.element) == ["none"]
    set_n(2)
    flush()
    assert texts(root_element.element) == ["5", "6"]


def test_repeat_count_expression_in_a_template_updates(wyb, root_element):
    items, set_items = create_signal(["a", "b"])
    wyb["reconciler"].render(html(t"<div>{Repeat(len(items()), lambda i: html(t'<b>{i}</b>'))}</div>"), root_element)
    assert texts(root_element.element) == ["0", "1"]
    set_items(["a", "b", "c"])
    flush()
    assert texts(root_element.element) == ["0", "1", "2"]


# ---------------------------------------------------------------------------
# Switch / Match
# ---------------------------------------------------------------------------


def test_switch_renders_first_matching_branch(wyb, root_element):
    status, set_status = create_signal("loading")
    view = html(
        t"""<div>{
            Switch(
                Match(lambda: status() == "loading", lambda: html(t"<p>Loading</p>")),
                Match(lambda: status() == "ready", lambda: html(t"<p>Ready</p>")),
                fallback=lambda: html(t"<p>?</p>"),
            )
        }</div>"""
    )
    wyb["reconciler"].render(view, root_element)
    assert texts(root_element.element) == ["Loading"]
    set_status("ready")
    flush()
    assert texts(root_element.element) == ["Ready"]
    set_status("zzz")
    flush()
    assert texts(root_element.element) == ["?"]


def test_switch_match_conditions_as_template_expressions(wyb, root_element):
    # `kind() == "a"` is dynamic: each `Match` receives a getter.
    kind, set_kind = create_signal("a")
    renders: list[str] = []

    def branch(name: str) -> Callable[[], Any]:
        def body() -> Any:
            renders.append(name)
            return html(t"<p>{name}</p>")

        return body

    view = html(
        t"""<div>{
            Switch(
                Match(kind() == "a", branch("A")),
                Match(kind() in ("b", "c"), branch("BC")),
                fallback=html(t"<p>other</p>"),
            )
        }</div>"""
    )
    wyb["reconciler"].render(view, root_element)
    assert texts(root_element.element) == ["A"]
    set_kind("b")
    flush()
    assert texts(root_element.element) == ["BC"]
    # The same branch keeps matching: not re-rendered.
    set_kind("c")
    flush()
    assert texts(root_element.element) == ["BC"]
    set_kind("z")
    flush()
    assert texts(root_element.element) == ["other"]
    assert renders == ["A", "BC"]


def test_switch_match_callback_receives_accessor(wyb, root_element):
    user, set_user = create_signal(None)
    admin, set_admin = create_signal(None)
    view = html(
        t"""<div>{
            Switch(
                Match(admin, lambda a: html(t"<p>admin {a()['name']}</p>")),
                Match(user, lambda u: html(t"<p>user {u()['name']}</p>")),
            )
        }</div>"""
    )
    wyb["reconciler"].render(view, root_element)
    assert texts(root_element.element) == []
    set_user({"name": "u"})
    flush()
    assert texts(root_element.element) == ["user ", "u"]
    set_admin({"name": "root"})
    flush()
    assert texts(root_element.element) == ["admin ", "root"]


def test_switch_keyed_match_recreates_on_value_change(wyb, root_element):
    value, set_value = create_signal("a")
    created: list[str] = []

    def body(v):
        created.append(v)
        return html(t"<p>{v}</p>")

    wyb["reconciler"].render(html(t"<div>{Switch(Match(value, body, keyed=True))}</div>"), root_element)
    set_value("b")
    flush()
    assert texts(root_element.element) == ["b"]
    assert created == ["a", "b"]


# ---------------------------------------------------------------------------
# dynamic
# ---------------------------------------------------------------------------


def test_dynamic_switches_tag(wyb, root_element):
    tag, set_tag = create_signal("h1")
    Heading = dynamic(tag)
    wyb["reconciler"].render(html(t"<div>{Heading(children='T', class_='x')}</div>"), root_element)
    outer = elements(root_element.element)[0]
    assert elements(outer)[0].tag == "h1"
    assert elements(outer)[0].attributes["class"] == "x"
    assert texts(root_element.element) == ["T"]
    set_tag("h2")
    flush()
    assert elements(outer)[0].tag == "h2"


def test_dynamic_switches_component_and_passes_props(wyb, root_element):
    @component
    def A(props: LabelProps):
        return html(t"<h1>A:{props.label}</h1>")

    @component
    def B(props: LabelProps):
        return html(t"<h2>B:{props.label}</h2>")

    which, set_which = create_signal(A)
    label, set_label = create_signal("x")
    View = dynamic(which)
    wyb["reconciler"].render(html(t"<div>{View(label=label())}</div>"), root_element)
    assert texts(root_element.element) == ["A:", "x"]
    set_label("y")
    flush()
    assert texts(root_element.element) == ["A:", "y"]
    set_which(lambda _: B)
    flush()
    assert texts(root_element.element) == ["B:", "y"]


def test_dynamic_as_a_component_tag(wyb, root_element):
    @component
    def A(props: LabelProps):
        return html(t"<h1>A:{props.label}</h1>")

    @component
    def B(props: LabelProps):
        return html(t"<h2>B:{props.label}</h2>")

    which, set_which = create_signal(A)
    label, set_label = create_signal("x")
    View = dynamic(which)
    wyb["reconciler"].render(html(t"<div><{View} label={label()} /></div>"), root_element)
    assert texts(root_element.element) == ["A:", "x"]
    set_which(lambda _: B)
    set_label("z")
    flush()
    assert texts(root_element.element) == ["B:", "z"]


def test_dynamic_with_static_component(wyb, root_element):
    @component
    def A():
        return html(t"<span>a</span>")

    View = dynamic(A)
    wyb["reconciler"].render(html(t"<div>{View()}</div>"), root_element)
    assert texts(root_element.element) == ["a"]


def test_dynamic_accepts_positional_children(wyb, root_element):
    Heading = dynamic("h2")
    wyb["reconciler"].render(html(t"<div>{Heading('Heading', html(t'<span>!</span>'))}</div>"), root_element)
    outer = elements(root_element.element)[0]
    assert elements(outer)[0].tag == "h2"
    assert texts(root_element.element) == ["Heading", "!"]


def test_dynamic_factory_is_a_reusable_component(wyb, root_element):
    @component
    def A(props: LabelProps):
        return html(t"<h1>A:{props.label}</h1>")

    @component
    def B(props: LabelProps):
        return html(t"<h2>B:{props.label}</h2>")

    rich, set_rich = create_signal(False)
    Editor = dynamic(lambda: B if rich() else A)
    assert repr(Editor) == "dynamic(...)"
    wyb["reconciler"].render(html(t"<div>{Editor(label='x')}{Editor(label='y')}</div>"), root_element)
    assert texts(root_element.element) == ["A:", "x", "A:", "y"]
    set_rich(True)
    flush()
    assert texts(root_element.element) == ["B:", "x", "B:", "y"]


def test_dynamic_with_item_syntax_children(wyb, root_element):
    tag, set_tag = create_signal("section")
    Box = dynamic(tag)
    wyb["reconciler"].render(
        html(t"<div>{Box(class_='box')[html(t'<p>a</p>'), html(t'<p>b</p>')]}</div>"), root_element
    )
    outer = elements(root_element.element)[0]
    assert elements(outer)[0].tag == "section"
    assert texts(root_element.element) == ["a", "b"]
    set_tag("article")
    flush()
    assert elements(outer)[0].tag == "article"
    assert texts(root_element.element) == ["a", "b"]


# ---------------------------------------------------------------------------
# NoHydration / Hydration / client_only (client render, no server HTML)
# ---------------------------------------------------------------------------


def test_no_hydration_renders_children_normally_in_a_client_render(wyb, root_element):
    n, set_n = create_signal(1)
    seen: list[bool] = []

    @component
    def Probe():
        seen.append(is_hydrating())
        return html(t"<span>probe</span>")

    view = html(
        t"""<div>{NoHydration(html(t"<p>static</p>"), html(t"<p>n={n()}</p>"), Probe())}<span>after</span></div>"""
    )
    root = wyb["reconciler"].render(view, root_element)
    assert texts(root_element.element) == ["static", "n=", "1", "probe", "after"]
    assert seen == [False]
    assert is_hydrating() is False
    # Outside hydration the region is ordinary, live content.
    set_n(2)
    flush()
    assert texts(root_element.element) == ["static", "n=", "2", "probe", "after"]
    root.dispose()
    assert texts(root_element.element) == []


def test_hydration_is_a_passthrough_in_a_client_render(wyb, root_element):
    n, set_n = create_signal(0)
    view = html(
        t"""<div>{NoHydration(html(t"<p>outer</p>"), Hydration(html(t"<p>island {n()}</p>"), id="isle"))}</div>"""
    )
    wyb["reconciler"].render(view, root_element)
    assert texts(root_element.element) == ["outer", "island ", "0"]
    set_n(1)
    flush()
    assert texts(root_element.element) == ["outer", "island ", "1"]


def test_no_hydration_toggled_by_show_mounts_and_unmounts(wyb, root_element):
    on, set_on = create_signal(True)
    view = html(t"""<div>{Show(on, lambda: NoHydration(html(t"<p>a</p>"), html(t"<p>b</p>")))}<p>tail</p></div>""")
    wyb["reconciler"].render(view, root_element)
    assert texts(root_element.element) == ["a", "b", "tail"]
    set_on(False)
    flush()
    assert texts(root_element.element) == ["tail"]
    set_on(True)
    flush()
    assert texts(root_element.element) == ["a", "b", "tail"]


def test_client_only_renders_children_immediately_without_server_html(wyb, root_element):
    view = html(t"<div>{client_only(lambda: html(t'<p>client</p>'), fallback=html(t'<p>server</p>'))}</div>")
    wyb["reconciler"].render(view, root_element)
    assert texts(root_element.element) == ["client"]


# ---------------------------------------------------------------------------
# on_hydration_end
# ---------------------------------------------------------------------------


def test_on_hydration_end_outside_hydration_runs_on_the_next_tick():
    log: list[str] = []

    async def main() -> None:
        on_hydration_end(lambda: log.append("end"))
        # Not synchronous: it waits for the next tick.
        assert log == []
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    asyncio.run(main())
    assert log == ["end"]
