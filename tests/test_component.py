"""The run-once component model: @component binding, Prop accessors, lifecycle."""

from __future__ import annotations

from conftest import StubNode, collect_texts

from wybthon import _warnings
from wybthon.component import Component, component
from wybthon.html import button, div, p, span
from wybthon.reactivity import (
    Prop,
    Props,
    create_effect,
    create_memo,
    create_signal,
    flush,
    on_cleanup,
    on_settled,
    prop,
)
from wybthon.vnode import VNode


def texts(node: StubNode) -> list[str]:
    return [t for t in collect_texts(node) if t]


def elements(node: StubNode) -> list[StubNode]:
    return [n for n in node.childNodes if n.tag]


# ---------------------------------------------------------------------------
# Declaration and calling
# ---------------------------------------------------------------------------


def test_component_call_returns_vnode_with_children_prop(wyb):
    @component
    def Card(title: Prop[str], children: Prop[list] = prop(None)):
        return div(title, children)

    assert isinstance(Card, Component)
    assert component(Card) is Card
    node = Card("a", "b", title="T")
    assert isinstance(node, VNode)
    assert node.props["title"] == "T"
    assert node.props["children"] == ["a", "b"]
    assert Card.defaults == {"children": None}
    assert repr(Card).startswith("<component ")


def test_component_preserves_function_metadata(wyb):
    @component
    def Named():
        """Doc."""
        return div()

    assert Named.__name__ == "Named"
    assert Named.__doc__ == "Doc."


# ---------------------------------------------------------------------------
# Prop binding
# ---------------------------------------------------------------------------


def test_parameters_are_props_with_defaults(wyb, root_element):
    seen: dict[str, object] = {}

    @component
    def Greeting(name: Prop[str] = prop("world"), excited: Prop[bool] = prop(False)):
        seen["name"] = name
        seen["excited"] = excited
        return p("Hello, ", name)

    wyb["reconciler"].render(Greeting(), root_element)
    assert isinstance(seen["name"], Prop)
    assert seen["name"].peek() == "world"
    assert seen["excited"].peek() is False
    assert texts(root_element.element) == ["Hello, ", "world"]


def test_plain_values_and_accessors_are_both_reactive_props(wyb, root_element):
    name, set_name = create_signal("Ada")

    @component
    def Greeting(name: Prop[str], suffix: Prop[str] = prop("")):
        return p(name, suffix)

    wyb["reconciler"].render(Greeting(name=name, suffix="!"), root_element)
    assert texts(root_element.element) == ["Ada", "!"]
    set_name("Grace")
    flush()
    assert texts(root_element.element) == ["Grace", "!"]


def test_body_runs_once_even_when_props_change(wyb, root_element):
    count, set_count = create_signal(0)
    runs: list[int] = []

    @component
    def Counter(value: Prop[int]):
        runs.append(1)
        return p(lambda: f"n={value()}")

    wyb["reconciler"].render(Counter(value=count), root_element)
    set_count(1)
    flush()
    set_count(2)
    flush()
    assert texts(root_element.element) == ["n=2"]
    assert runs == [1]


def test_parent_rerender_patches_child_props_without_remount(wyb, root_element):
    label, set_label = create_signal("a")
    runs: list[int] = []

    @component
    def Child(text: Prop[str]):
        runs.append(1)
        return span(text)

    # The parent's hole re-renders a new VNode for Child with a plain value;
    # the mounted Child receives the new value through its live Prop.
    wyb["reconciler"].render(div(lambda: Child(text=label())), root_element)
    assert texts(root_element.element) == ["a"]
    set_label("b")
    flush()
    assert texts(root_element.element) == ["b"]
    assert runs == [1]


def test_var_keyword_collects_rest_props(wyb, root_element):
    seen: dict[str, object] = {}

    @component
    def Button(label: Prop[str], **rest):
        seen.update(rest)
        return button(label, **{k: v for k, v in rest.items()})

    wyb["reconciler"].render(Button(label="Go", class_="primary", id="b1"), root_element)
    assert set(seen) == {"class_", "id"}
    assert all(isinstance(v, Prop) for v in seen.values())
    btn = elements(root_element.element)[0]
    assert btn.attributes["id"] == "b1"
    assert btn.attributes["class"] == "primary"


def test_single_positional_param_receives_props_mapping(wyb, root_element):
    seen: list[Props] = []

    def Raw(props):
        seen.append(props)
        return p(props.title)

    wyb["reconciler"].render(component(Raw)(title="T"), root_element)
    assert isinstance(seen[0], Props)
    assert seen[0].title() == "T"
    assert texts(root_element.element) == ["T"]


def test_props_annotation_receives_props_mapping(wyb, root_element):
    seen: list[Props] = []

    @component
    def Raw(props: Props):
        seen.append(props)
        return p(props.raw("title"))

    wyb["reconciler"].render(Raw(title="T"), root_element)
    assert isinstance(seen[0], Props)
    assert texts(root_element.element) == ["T"]


def test_prop_peek_is_untracked(wyb, root_element):
    count, set_count = create_signal(0)
    runs: list[int] = []

    @component
    def Peeker(value: Prop[int]):
        def view():
            runs.append(1)
            return str(value.peek())

        return p(view)

    wyb["reconciler"].render(Peeker(value=count), root_element)
    set_count(1)
    flush()
    assert texts(root_element.element) == ["0"]
    assert runs == [1]


def test_callback_props_pass_through_raw(wyb, root_element):
    calls: list[str] = []

    @component
    def Clicker(on_pick: Prop):
        return button("x", on_click=lambda e: on_pick()("picked"))

    wyb["reconciler"].render(Clicker(on_pick=calls.append), root_element)
    btn = elements(root_element.element)[0]
    wyb["kernel"]._backend.dispatch("click", btn)
    assert calls == ["picked"]


def test_component_returning_string_list_or_none(wyb, root_element):
    @component
    def Text():
        return "plain"

    @component
    def Many():
        return [span("a"), span("b")]

    @component
    def Nothing():
        return None

    wyb["reconciler"].render(div(Text(), Many(), Nothing()), root_element)
    assert texts(root_element.element) == ["plain", "a", "b"]


def test_component_returning_accessor_is_reactive(wyb, root_element):
    n, set_n = create_signal(1)

    @component
    def Value():
        return create_memo(lambda: f"v{n()}")

    wyb["reconciler"].render(div(Value()), root_element)
    assert texts(root_element.element) == ["v1"]
    set_n(2)
    flush()
    assert texts(root_element.element) == ["v2"]


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


def test_on_settled_runs_after_mount_and_cleanup_on_unmount(wyb, root_element):
    log: list[str] = []
    show, set_show = create_signal(True)

    @component
    def Widget():
        def start():
            log.append(f"settled:{len(texts(root_element.element))}")
            return lambda: log.append("cleanup")

        on_settled(start)
        on_cleanup(lambda: log.append("unmount"))
        return p("w")

    wyb["reconciler"].render(div(lambda: Widget() if show() else None), root_element)
    assert log == ["settled:1"]
    set_show(False)
    flush()
    assert texts(root_element.element) == []
    assert sorted(log[1:]) == ["cleanup", "unmount"]


def test_cleanup_may_write_signals_when_unmounted_from_a_hole(wyb, root_element):
    show, set_show = create_signal(True)
    unmounts, set_unmounts = create_signal(0)

    @component
    def Widget():
        on_cleanup(lambda: set_unmounts(lambda n: n + 1))
        return p("w")

    wyb["reconciler"].render(div(lambda: Widget() if show() else None, span(lambda: str(unmounts()))), root_element)
    set_show(False)
    flush()
    assert texts(root_element.element) == ["1"]
    set_show(True)
    flush()
    set_show(False)
    flush()
    assert texts(root_element.element) == ["2"]


def test_effects_in_component_body_are_disposed_on_unmount(wyb, root_element):
    show, set_show = create_signal(True)
    tick, set_tick = create_signal(0)
    seen: list[int] = []

    @component
    def Watcher():
        create_effect(tick, lambda v: seen.append(v))
        return p("w")

    wyb["reconciler"].render(div(lambda: Watcher() if show() else None), root_element)
    flush()
    assert seen == [0]
    set_tick(1)
    flush()
    assert seen == [0, 1]
    set_show(False)
    flush()
    set_tick(2)
    flush()
    assert seen == [0, 1]


def test_effect_in_body_observes_mounted_dom(wyb, root_element):
    counts: list[int] = []

    @component
    def Widget():
        create_effect(lambda: None, lambda _: counts.append(len(texts(root_element.element))))
        return p("mounted")

    wyb["reconciler"].render(Widget(), root_element)
    flush()
    assert counts == [1]


def test_top_level_prop_read_warns_in_dev_mode(wyb, root_element, capsys):
    _warnings._reset_warning_dedupe()

    @component
    def Bad(name: Prop[str]):
        value = name()
        return p(value)

    wyb["reconciler"].render(Bad(name="x"), root_element)
    err = capsys.readouterr().err
    assert "Warning" in err
    assert "name" in err


def test_top_level_read_does_not_warn_when_peeked_or_untracked(wyb, root_element, capsys):
    _warnings._reset_warning_dedupe()

    @component
    def Fine(name: Prop[str]):
        value = name.peek()
        return p(value)

    wyb["reconciler"].render(Fine(name="x"), root_element)
    assert capsys.readouterr().err == ""


def test_nested_components_and_keyed_remount(wyb, root_element):
    key, set_key = create_signal("a")
    mounted: list[str] = []

    @component
    def Leaf(tag: Prop[str]):
        mounted.append(tag.peek())
        on_cleanup(lambda: mounted.append(f"-{tag.peek()}"))
        return span(tag)

    @component
    def Tree():
        return div(lambda: Leaf(tag=key(), key=key()))

    wyb["reconciler"].render(Tree(), root_element)
    set_key("b")
    flush()
    assert texts(root_element.element) == ["b"]
    assert mounted == ["a", "-a", "b"]
