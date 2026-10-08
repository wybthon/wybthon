"""The run-once component model: typed `Props`, `Prop` accessors, plain fields, and lifecycle."""

from collections.abc import Callable
from typing import Any

import pytest
from conftest import StubNode, collect_texts

from wybthon import _warnings
from wybthon.component import Component, component
from wybthon.html import button, div, h2, li, p, span, ul
from wybthon.reactivity import (
    ChildrenAccessor,
    ParentProps,
    Prop,
    Props,
    children,
    create_effect,
    create_memo,
    create_reaction,
    create_root,
    create_signal,
    flush,
    on_cleanup,
    on_settled,
    prop,
)
from wybthon.vnode import VNode


def texts(node: StubNode) -> list[str]:
    return [t for t in collect_texts(node) if t and t.strip()]


def elements(node: StubNode) -> list[StubNode]:
    return [n for n in node.childNodes if n.tag]


@pytest.fixture()
def dev_mode():
    """Run with dev mode on, restoring the previous setting afterward."""
    previous = _warnings.is_dev_mode()
    _warnings.set_dev_mode(True)
    try:
        yield
    finally:
        _warnings.set_dev_mode(previous)


# ---------------------------------------------------------------------------
# Declaration and calling
# ---------------------------------------------------------------------------


def test_component_call_returns_vnode_with_children_prop(wyb):
    class CardProps(ParentProps):
        title: Prop[str]

    @component
    def Card(props: CardProps):
        return div(props.title, props.children)

    assert isinstance(Card, Component)
    assert component(Card) is Card
    node = Card("a", "b", title="T")
    assert isinstance(node, VNode)
    assert node.props["title"] == "T"
    assert node.props["children"] == ["a", "b"]
    assert repr(Card).startswith("<component ")


def test_component_preserves_function_metadata(wyb):
    @component
    def Named():
        """Doc."""
        return div()

    assert Named.__name__ == "Named"
    assert Named.__doc__ == "Doc."


def test_children_keyword_and_item_syntax_on_components(wyb, root_element):
    class CardProps(ParentProps):
        title: Prop[str]

    @component
    def Card(props: CardProps):
        return div(h2(props.title), props.children)

    by_item = Card(title="Hi")[p("a"), p("b")]
    assert isinstance(by_item, VNode)
    assert [c.tag for c in by_item.props["children"]] == ["p", "p"]
    by_keyword = Card(title="Kw", children=[p("c")])
    wyb["reconciler"].render(div(by_item, by_keyword), root_element)
    assert texts(root_element.element) == ["Hi", "a", "b", "Kw", "c"]


def test_item_syntax_on_elements_sets_child_nodes(wyb, root_element):
    node = div(class_="card")[h2("Title"), p("Body")]
    assert isinstance(node, VNode)
    assert [c.tag for c in node.children] == ["h2", "p"]
    single = ul()[li("only")]
    assert [c.tag for c in single.children] == ["li"]
    wyb["reconciler"].render(div(node, single), root_element)
    assert texts(root_element.element) == ["Title", "Body", "only"]
    card = elements(root_element.element.childNodes[0])[0]
    assert card.attributes["class"] == "card"


# ---------------------------------------------------------------------------
# Typed Props: validation and declaration
# ---------------------------------------------------------------------------


def test_missing_required_and_unknown_props_raise_in_dev_mode(wyb, dev_mode):
    class GreetingProps(Props):
        name: Prop[str]
        excited: Prop[bool] = prop(default=False)

    @component
    def Greeting(props: GreetingProps):
        return p(props.name)

    with pytest.raises(TypeError, match=r"missing required prop\(s\): name"):
        Greeting()
    with pytest.raises(TypeError, match=r"unexpected prop\(s\): bogus"):
        Greeting(name="x", bogus=1)
    # `key` and the declared fields are always accepted.
    assert isinstance(Greeting(name="x", excited=True, key="k"), VNode)


def test_component_without_props_rejects_props_but_accepts_key(wyb, dev_mode):
    @component
    def Plain():
        return p("x")

    with pytest.raises(TypeError, match="takes no props"):
        Plain(title="x")
    assert Plain(key="k").key == "k"


def test_prop_validation_is_skipped_in_production_mode(wyb):
    class GreetingProps(Props):
        name: Prop[str]

    @component
    def Greeting(props: GreetingProps):
        return p(props.name)

    previous = _warnings.is_dev_mode()
    _warnings.set_dev_mode(False)
    try:
        assert isinstance(Greeting(bogus=1), VNode)
    finally:
        _warnings.set_dev_mode(previous)


def test_parameters_that_are_not_a_props_class_are_rejected(wyb, dev_mode):
    @component
    def Untyped(count):
        return p(str(count))

    @component
    def Keyword(*, props: Props):
        return p("x")

    @component
    def Two(a: Props, b: Props):
        return p("x")

    for comp in (Untyped, Keyword, Two):
        with pytest.raises(TypeError, match="must take no parameters or one parameter annotated with a Props subclass"):
            comp()


def test_base_props_annotation_accepts_only_key(wyb, root_element, dev_mode):
    seen: list[Props] = []

    @component
    def Raw(props: Props):
        seen.append(props)
        return p("raw")

    with pytest.raises(TypeError, match="unexpected prop"):
        Raw(title="T")
    wyb["reconciler"].render(Raw(key="k"), root_element)
    assert isinstance(seen[0], Props)
    assert texts(root_element.element) == ["raw"]


def test_prop_requires_exactly_one_keyword_default(wyb):
    with pytest.raises(TypeError):
        prop()
    with pytest.raises(TypeError):
        prop(default=1, default_factory=list)
    with pytest.raises(TypeError):
        prop(1)
    with pytest.raises(TypeError, match="prop\\(\\) is for Prop\\[T\\] fields"):

        class Bad(Props):
            count: int = prop(default=1)


def test_props_are_read_only(wyb, root_element):
    class P(Props):
        name: Prop[str] = prop(default="x")
        tag: str = "t"

    errors: list[str] = []

    @component
    def Comp(props: P):
        for field in ("name", "tag"):
            try:
                setattr(props, field, "y")
            except AttributeError as exc:
                errors.append(str(exc))
        return p(props.name)

    wyb["reconciler"].render(Comp(), root_element)
    assert errors == ["Component props are read-only"] * 2


# ---------------------------------------------------------------------------
# Prop binding
# ---------------------------------------------------------------------------


def test_prop_fields_are_accessors_with_defaults(wyb, root_element):
    seen: dict[str, object] = {}

    class GreetingProps(Props):
        name: Prop[str] = prop(default="world")
        excited: Prop[bool] = prop(default=False)

    @component
    def Greeting(props: GreetingProps):
        seen["name"] = props.name
        seen["excited"] = props.excited
        return p("Hello, ", props.name)

    wyb["reconciler"].render(Greeting(), root_element)
    assert callable(seen["name"])
    assert seen["name"].peek() == "world"
    assert seen["excited"].peek() is False
    assert texts(root_element.element) == ["Hello, ", "world"]


def test_prop_default_factory_gives_each_instance_its_own_value(wyb, root_element):
    lists: list[list[str]] = []

    class TagsProps(Props):
        tags: Prop[list[str]] = prop(default_factory=list)

    @component
    def Tags(props: TagsProps):
        value = props.tags.peek()
        value.append("x")
        lists.append(value)
        return p(str(len(value)))

    wyb["reconciler"].render(div(Tags(), Tags(), Tags(tags=["given"])), root_element)
    assert lists == [["x"], ["x"], ["given", "x"]]
    assert lists[0] is not lists[1]
    assert texts(root_element.element) == ["1", "1", "2"]


def test_plain_values_and_accessors_are_both_reactive_props(wyb, root_element):
    name, set_name = create_signal("Ada")

    class GreetingProps(Props):
        name: Prop[str]
        suffix: Prop[str] = prop(default="")

    @component
    def Greeting(props: GreetingProps):
        return p(props.name, props.suffix)

    wyb["reconciler"].render(Greeting(name=name, suffix="!"), root_element)
    assert texts(root_element.element) == ["Ada", "!"]
    set_name("Grace")
    flush()
    assert texts(root_element.element) == ["Grace", "!"]


def test_body_runs_once_even_when_props_change(wyb, root_element):
    count, set_count = create_signal(0)
    runs: list[int] = []

    class CounterProps(Props):
        value: Prop[int]

    @component
    def Counter(props: CounterProps):
        runs.append(1)
        return p(lambda: f"n={props.value()}")

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

    class ChildProps(Props):
        text: Prop[str]

    @component
    def Child(props: ChildProps):
        runs.append(1)
        return span(props.text)

    # The parent's hole re-renders a new VNode for Child with a plain value;
    # the mounted Child receives the new value through its live Prop.
    wyb["reconciler"].render(div(lambda: Child(text=label())), root_element)
    assert texts(root_element.element) == ["a"]
    set_label("b")
    flush()
    assert texts(root_element.element) == ["b"]
    assert runs == [1]


def test_parent_updates_flow_into_prop_accessors_and_plain_fields(wyb, root_element):
    n, set_n = create_signal(1)
    runs: list[int] = []
    seen: list[tuple[int, str]] = []
    reads: list[Callable[[], tuple[int, str]]] = []

    class ChildProps(Props):
        value: Prop[int]
        mode: str = "plain"

    @component
    def Child(props: ChildProps):
        runs.append(1)
        create_effect(props.value, lambda v: seen.append((v, props.mode)))
        reads.append(lambda: (props.value.peek(), props.mode))
        return span(lambda: str(props.value() * 10))

    wyb["reconciler"].render(div(lambda: Child(value=n(), mode=f"m{n()}")), root_element)
    flush()
    assert texts(root_element.element) == ["10"]
    set_n(2)
    flush()
    assert texts(root_element.element) == ["20"]
    assert runs == [1]
    assert seen == [(1, "m1"), (2, "m2")]
    # A plain field reads the parent's latest value (untracked).
    assert reads[0]() == (2, "m2")


def test_omitted_prop_falls_back_to_default_after_parent_update(wyb, root_element):
    with_label, set_with_label = create_signal(True)

    class LabelProps(Props):
        label: Prop[str] = prop(default="default")

    @component
    def Label(props: LabelProps):
        return span(props.label)

    wyb["reconciler"].render(div(lambda: Label(label="given") if with_label() else Label()), root_element)
    assert texts(root_element.element) == ["given"]
    set_with_label(False)
    flush()
    assert texts(root_element.element) == ["default"]


def test_omit_props_with_names_and_predicate_spreads_onto_elements(wyb, root_element):
    from wybthon.reactivity import omit

    cls, set_cls = create_signal("primary")

    class ButtonProps(Props):
        label: Prop[str]
        class_: Prop[str | None] = prop(default=None)
        id: Prop[str | None] = prop(default=None)
        title: Prop[str | None] = prop(default=None)

    rest_keys: list[list[str]] = []

    @component
    def Button(props: ButtonProps):
        rest = omit(props, "label")
        rest_keys.append(sorted(rest))
        no_title = omit(props, lambda key: key in ("label", "title"))
        rest_keys.append(sorted(no_title))
        return button(props.label, **no_title)

    wyb["reconciler"].render(Button(label="Go", class_=cls, id="b1", title="t"), root_element)
    assert rest_keys == [["class_", "id", "title"], ["class_", "id"]]
    btn = elements(root_element.element)[0]
    assert btn.attributes["id"] == "b1"
    assert btn.attributes["class"] == "primary"
    assert "title" not in btn.attributes
    set_cls("secondary")
    flush()
    assert btn.attributes["class"] == "secondary"


def test_prop_peek_is_untracked(wyb, root_element):
    count, set_count = create_signal(0)
    runs: list[int] = []

    class PeekerProps(Props):
        value: Prop[int]

    @component
    def Peeker(props: PeekerProps):
        def view():
            runs.append(1)
            return str(props.value.peek())

        return p(view)

    wyb["reconciler"].render(Peeker(value=count), root_element)
    set_count(1)
    flush()
    assert texts(root_element.element) == ["0"]
    assert runs == [1]


def test_callback_fields_pass_through_untouched(wyb, root_element):
    calls: list[str] = []

    class ClickerProps(Props):
        on_pick: Callable[[str], None]

    @component
    def Clicker(props: ClickerProps):
        return button("x", on_click=lambda e: props.on_pick("picked"))

    wyb["reconciler"].render(Clicker(on_pick=calls.append), root_element)
    btn = elements(root_element.element)[0]
    wyb["kernel"]._backend.dispatch("click", btn)
    assert calls == ["picked"]


def test_zero_arg_callable_plain_fields_are_never_called_on_read(wyb, root_element):
    calls: list[str] = []
    seen: list[Any] = []
    close = lambda: calls.append("closed")  # noqa: E731

    class DialogProps(Props):
        on_close: Callable[[], None] | None = None
        make_label: Callable[[], str] = lambda: "default"  # noqa: E731

    @component
    def Dialog(props: DialogProps):
        seen.append(props.on_close)
        seen.append(props.on_close)
        return button("close", on_click=lambda: props.on_close() if props.on_close else None)

    wyb["reconciler"].render(Dialog(on_close=close), root_element)
    assert seen == [close, close]
    assert calls == []
    wyb["kernel"]._backend.dispatch("click", elements(root_element.element)[0])
    flush()
    assert calls == ["closed"]


def test_plain_field_default_is_returned_when_not_passed(wyb, root_element):
    seen: list[Any] = []

    class P(Props):
        size: int = 3
        handler: Callable[[], None] | None = None

    @component
    def Comp(props: P):
        seen.extend([props.size, props.handler])
        return p(str(props.size))

    wyb["reconciler"].render(Comp(), root_element)
    assert seen == [3, None]
    assert texts(root_element.element) == ["3"]


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
# children()
# ---------------------------------------------------------------------------


def test_children_helper_resolves_props_children_and_to_array(wyb, root_element):
    extra, set_extra = create_signal(False)
    counts: list[int] = []

    @component
    def Tabs(props: ParentProps):
        kids = children(props.children)
        assert isinstance(kids, ChildrenAccessor)
        counts.append(len(kids.to_array()))
        return ul(lambda: [li(k) for k in kids.to_array()])

    wyb["reconciler"].render(Tabs()["one", None, ["two", lambda: "three" if extra() else None]], root_element)
    assert texts(root_element.element) == ["one", "two"]
    assert counts == [2]
    set_extra(True)
    flush()
    assert texts(root_element.element) == ["one", "two", "three"]


def test_children_accessor_returns_single_child_or_list(wyb):
    kids, set_kids = create_signal(["a", None, ["b", ["c"]]])
    resolved = create_root(lambda d: children(kids))
    assert resolved() == ["a", "b", "c"]
    assert resolved.to_array() == ["a", "b", "c"]
    set_kids("solo")
    flush()
    assert resolved() == "solo"
    assert resolved.to_array() == ["solo"]
    set_kids(None)
    flush()
    assert resolved() == []
    assert resolved.to_array() == []


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


def test_create_reaction_fires_once_per_track_and_is_disposed_with_component(wyb, root_element):
    count, set_count = create_signal(0)
    show, set_show = create_signal(True)
    fired: list[int] = []
    trackers: list[Callable[[Callable[[], Any]], None]] = []

    @component
    def Watcher():
        track = create_reaction(lambda: fired.append(count.peek()))
        track(count)
        trackers.append(track)
        return p("w")

    wyb["reconciler"].render(div(lambda: Watcher() if show() else None), root_element)
    flush()
    assert fired == []
    set_count(1)
    flush()
    assert fired == [1]
    # The subscription ended after firing; another change is ignored until re-armed.
    set_count(2)
    flush()
    assert fired == [1]
    trackers[0](count)
    set_count(3)
    flush()
    assert fired == [1, 3]
    trackers[0](count)
    set_show(False)
    flush()
    set_count(4)
    flush()
    assert fired == [1, 3]


def test_top_level_prop_read_warns_in_dev_mode(wyb, root_element, capsys, dev_mode):
    _warnings._reset_warning_dedupe()

    class BadProps(Props):
        name: Prop[str]

    @component
    def Bad(props: BadProps):
        value = props.name()
        return p(value)

    wyb["reconciler"].render(Bad(name="x"), root_element)
    err = capsys.readouterr().err
    assert "Warning" in err
    assert "name" in err


def test_top_level_read_does_not_warn_when_peeked_or_untracked(wyb, root_element, capsys, dev_mode):
    _warnings._reset_warning_dedupe()

    class FineProps(Props):
        name: Prop[str]
        on_done: Callable[[], None] | None = None

    @component
    def Fine(props: FineProps):
        value = props.name.peek()
        _ = props.on_done
        return p(value)

    wyb["reconciler"].render(Fine(name="x"), root_element)
    assert capsys.readouterr().err == ""


def test_nested_components_and_keyed_remount(wyb, root_element):
    key, set_key = create_signal("a")
    mounted: list[str] = []

    class LeafProps(Props):
        tag: Prop[str]

    @component
    def Leaf(props: LeafProps):
        tag = props.tag.peek()
        mounted.append(tag)
        on_cleanup(lambda: mounted.append(f"-{tag}"))
        return span(props.tag)

    @component
    def Tree():
        return div(lambda: Leaf(tag=key(), key=key()))

    wyb["reconciler"].render(Tree(), root_element)
    set_key("b")
    flush()
    assert texts(root_element.element) == ["b"]
    assert mounted == ["a", "-a", "b"]


def test_same_key_patches_and_new_key_remounts(wyb, root_element):
    state, set_state = create_signal(("k1", "a"))
    mounted: list[str] = []

    class LeafProps(Props):
        text: Prop[str]

    @component
    def Leaf(props: LeafProps):
        mounted.append(props.text.peek())
        return span(props.text)

    wyb["reconciler"].render(div(lambda: Leaf(text=state()[1], key=state()[0])), root_element)
    set_state(("k1", "b"))
    flush()
    assert texts(root_element.element) == ["b"]
    assert mounted == ["a"]
    set_state(("k2", "c"))
    flush()
    assert texts(root_element.element) == ["c"]
    assert mounted == ["a", "c"]


def test_typed_default_and_bound_method_accessors_render(wyb, root_element):
    name, set_name = create_signal("Ada")

    class Model:
        def name(self):
            return name()

    class GreetingProps(Props):
        name: Prop[str]
        copies: Prop[int] = prop(default=2)

    @component
    def Greeting(props: GreetingProps):
        return p(lambda: props.name() * props.copies())

    wyb["reconciler"].render(Greeting(name=Model().name), root_element)
    assert texts(root_element.element) == ["AdaAda"]
    set_name("Grace")
    flush()
    assert texts(root_element.element) == ["GraceGrace"]


def test_string_annotation_resolves_to_module_level_props(wyb, root_element):
    @component
    def Card(props: "_ModuleCardProps"):
        return p(props.title)

    wyb["reconciler"].render(Card(title="bound"), root_element)
    assert texts(root_element.element) == ["bound"]


class _ModuleCardProps(Props):
    title: Prop[str]
