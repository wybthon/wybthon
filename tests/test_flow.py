"""Control flow: Show, For, Repeat, Switch/Match, Dynamic."""

from __future__ import annotations

from conftest import StubNode, collect_texts

from wybthon import _warnings
from wybthon.component import component
from wybthon.flow import Dynamic, For, Match, Repeat, Show, Switch, dynamic
from wybthon.html import div, h1, h2, li, p, span, ul
from wybthon.reactivity import Prop, create_signal, flush, on_cleanup


def texts(node: StubNode) -> list[str]:
    return [t for t in collect_texts(node) if t]


def elements(node: StubNode) -> list[StubNode]:
    return [n for n in node.childNodes if n.tag]


# ---------------------------------------------------------------------------
# Show
# ---------------------------------------------------------------------------


def test_show_toggles_children_and_fallback(wyb, root_element):
    on, set_on = create_signal(False)
    wyb["reconciler"].render(div(Show(on, lambda: p("yes"), fallback=lambda: p("no"))), root_element)
    assert texts(root_element.element) == ["no"]
    set_on(True)
    flush()
    assert texts(root_element.element) == ["yes"]
    set_on(False)
    flush()
    assert texts(root_element.element) == ["no"]


def test_show_accepts_static_vnode_children(wyb, root_element):
    on, set_on = create_signal(True)
    wyb["reconciler"].render(div(Show(on, p("static"))), root_element)
    assert texts(root_element.element) == ["static"]
    set_on(False)
    flush()
    assert texts(root_element.element) == []


def test_show_callback_receives_accessor_and_is_not_recreated(wyb, root_element):
    user, set_user = create_signal(None)
    created: list[int] = []

    def body(u):
        created.append(1)
        return p("hi ", lambda: u()["name"])

    wyb["reconciler"].render(div(Show(user, body)), root_element)
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
        return p(u["name"])

    wyb["reconciler"].render(div(Show(user, body, keyed=True)), root_element)
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
        return p("c")

    wyb["reconciler"].render(div(Show(on, lambda: Child())), root_element)
    set_on(False)
    flush()
    assert log == ["cleanup"]


def test_show_does_not_rerender_on_truthy_to_truthy_change(wyb, root_element):
    count, set_count = create_signal(1)
    renders: list[int] = []
    wyb["reconciler"].render(div(Show(count, lambda: (renders.append(1), p("on"))[1])), root_element)
    set_count(2)
    flush()
    assert renders == [1]


# ---------------------------------------------------------------------------
# For
# ---------------------------------------------------------------------------


def _items(*ids: int) -> list[dict]:
    return [{"id": i, "t": f"t{i}"} for i in ids]


def test_for_renders_rows_and_fallback(wyb, root_element):
    items, set_items = create_signal([])
    wyb["reconciler"].render(ul(For(items, lambda item, i: li(item["t"]), fallback=lambda: li("empty"))), root_element)
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
        return li(lambda: f"{index()}:{item['t']}")

    wyb["reconciler"].render(ul(For(items, row)), root_element)
    assert texts(root_element.element) == ["0:t1", "1:t2"]
    ul_node = elements(root_element.element)[0]
    before = {n.nodeValue if False else id(n): n for n in elements(ul_node)}
    set_items([b, c, a])
    flush()
    assert texts(root_element.element) == ["0:t2", "1:t3", "2:t1"]
    assert created == [1, 2, 3]
    after = [id(n) for n in elements(ul_node)]
    assert set(before) <= set(after)


def test_for_rows_are_disposed_when_removed(wyb, root_element):
    a, b = _items(1, 2)
    items, set_items = create_signal([a, b])
    disposed: list[int] = []

    def row(item, index):
        on_cleanup(lambda: disposed.append(item["id"]))
        return li(item["t"])

    wyb["reconciler"].render(ul(For(items, row)), root_element)
    set_items([b])
    flush()
    assert disposed == [1]
    assert texts(root_element.element) == ["t2"]


def test_for_unkeyed_reuses_rows_by_position(wyb, root_element):
    items, set_items = create_signal(["a", "b"])
    created: list[int] = []

    def row(item, index):
        created.append(index)
        return li(lambda: f"{index}:{item()}")

    wyb["reconciler"].render(ul(For(items, row, keyed=False)), root_element)
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
        return li(lambda: f"{index()}:{item()['t']}")

    wyb["reconciler"].render(ul(For(items, row, keyed=lambda x: x["id"])), root_element)
    set_items([{"id": 2, "t": "new"}, {"id": 1, "t": "T1"}])
    flush()
    assert texts(root_element.element) == ["0:new", "1:T1"]
    assert created == [1, 2]


def test_for_with_plain_list_warns_once(wyb, root_element, capsys):
    _warnings._reset_warning_dedupe()
    wyb["reconciler"].render(ul(For(["a", "b"], lambda item, i: li(item))), root_element)
    assert texts(root_element.element) == ["a", "b"]
    assert "plain list" in capsys.readouterr().err


def test_for_rows_are_isolated_scopes(wyb, root_element):
    items, _ = create_signal(_items(1, 2))
    hits, set_hits = create_signal({1: 0, 2: 0})
    renders: list[int] = []

    def row(item, index):
        return li(lambda: (renders.append(item["id"]), str(hits()[item["id"]]))[1])

    wyb["reconciler"].render(ul(For(items, row)), root_element)
    set_hits({1: 1, 2: 0})
    flush()
    # Both holes read `hits`, so both re-render; the rows themselves are not
    # recreated (no extra row creation, only hole updates).
    assert texts(root_element.element) == ["1", "0"]
    assert renders.count(1) == 2 and renders.count(2) == 2


def test_for_inserted_rows_mount_in_document_order(wyb, root_element):
    from wybthon.reactivity import on_settled

    one = _items(1)
    items, set_items = create_signal(one)
    order: list[int] = []

    @component
    def Row(item: Prop[dict]):
        iid = item.peek()["id"]
        on_settled(lambda: order.append(iid))
        return li(str(iid))

    wyb["reconciler"].render(ul(For(items, lambda item, index: Row(item=item))), root_element)
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
    def Row(item: Prop[dict]):
        iid = item.peek()["id"]
        bodies.append(iid)
        return li(str(iid))

    wyb["reconciler"].render(ul(For(items, lambda item, index: Row(item=item))), root_element)
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
        return span(str(i))

    wyb["reconciler"].render(div(Repeat(n, row)), root_element)
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
    wyb["reconciler"].render(
        div(Repeat(n, lambda i: span(str(i)), fallback=lambda: span("none"), start=5)), root_element
    )
    assert texts(root_element.element) == ["none"]
    set_n(2)
    flush()
    assert texts(root_element.element) == ["5", "6"]


# ---------------------------------------------------------------------------
# Switch / Match
# ---------------------------------------------------------------------------


def test_switch_renders_first_matching_branch(wyb, root_element):
    status, set_status = create_signal("loading")
    wyb["reconciler"].render(
        div(
            Switch(
                Match(lambda: status() == "loading", lambda: p("Loading")),
                Match(lambda: status() == "ready", lambda: p("Ready")),
                fallback=lambda: p("?"),
            )
        ),
        root_element,
    )
    assert texts(root_element.element) == ["Loading"]
    set_status("ready")
    flush()
    assert texts(root_element.element) == ["Ready"]
    set_status("zzz")
    flush()
    assert texts(root_element.element) == ["?"]


def test_switch_match_callback_receives_accessor(wyb, root_element):
    user, set_user = create_signal(None)
    admin, set_admin = create_signal(None)
    wyb["reconciler"].render(
        div(
            Switch(
                Match(admin, lambda a: p("admin ", lambda: a()["name"])),
                Match(user, lambda u: p("user ", lambda: u()["name"])),
            )
        ),
        root_element,
    )
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
        return p(v)

    wyb["reconciler"].render(div(Switch(Match(value, body, keyed=True))), root_element)
    set_value("b")
    flush()
    assert texts(root_element.element) == ["b"]
    assert created == ["a", "b"]


# ---------------------------------------------------------------------------
# Dynamic
# ---------------------------------------------------------------------------


def test_dynamic_switches_tag(wyb, root_element):
    tag, set_tag = create_signal("h1")
    wyb["reconciler"].render(div(Dynamic(tag, children="T", class_="x")), root_element)
    outer = elements(root_element.element)[0]
    assert elements(outer)[0].tag == "h1"
    assert elements(outer)[0].attributes["class"] == "x"
    assert texts(root_element.element) == ["T"]
    set_tag("h2")
    flush()
    assert elements(outer)[0].tag == "h2"


def test_dynamic_switches_component_and_passes_props(wyb, root_element):
    @component
    def A(label: Prop[str]):
        return h1("A:", label)

    @component
    def B(label: Prop[str]):
        return h2("B:", label)

    which, set_which = create_signal(A)
    label, set_label = create_signal("x")
    wyb["reconciler"].render(div(Dynamic(which, label=label)), root_element)
    assert texts(root_element.element) == ["A:", "x"]
    set_label("y")
    flush()
    assert texts(root_element.element) == ["A:", "y"]
    set_which(lambda _: B)
    flush()
    assert texts(root_element.element) == ["B:", "y"]


def test_dynamic_with_static_component(wyb, root_element):
    @component
    def A():
        return span("a")

    wyb["reconciler"].render(div(Dynamic(A)), root_element)
    assert texts(root_element.element) == ["a"]


def test_dynamic_accepts_positional_children(wyb, root_element):
    wyb["reconciler"].render(div(Dynamic("h2", "Heading", span("!"))), root_element)
    outer = elements(root_element.element)[0]
    assert elements(outer)[0].tag == "h2"
    assert texts(root_element.element) == ["Heading", "!"]


def test_dynamic_factory_is_a_reusable_component(wyb, root_element):
    @component
    def A(label: Prop[str]):
        return h1("A:", label)

    @component
    def B(label: Prop[str]):
        return h2("B:", label)

    rich, set_rich = create_signal(False)
    Editor = dynamic(lambda: B if rich() else A)
    assert repr(Editor) == "dynamic(...)"
    wyb["reconciler"].render(div(Editor(label="x"), Editor(label="y")), root_element)
    assert texts(root_element.element) == ["A:", "x", "A:", "y"]
    set_rich(True)
    flush()
    assert texts(root_element.element) == ["B:", "x", "B:", "y"]
