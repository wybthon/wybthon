"""The run-once component model: typed `Props`, Solid-style prop reads, callable fields, and lifecycle."""

from collections.abc import Callable
from typing import Any

import pytest
from conftest import StubNode, collect_texts

from wybthon import _warnings, h, html
from wybthon.component import Component, component
from wybthon.reactivity import (
    ChildrenAccessor,
    ParentProps,
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
    untrack,
)
from wybthon.vnode import VNode


def texts(node: StubNode) -> list[str]:
    return [t for t in collect_texts(node) if t and t.strip()]


def text(node: StubNode) -> str:
    return "".join(texts(node))


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
        title: str

    @component
    def Card(props: CardProps):
        return html(t"<div>{props.title}{props.children}</div>")

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
        return html(t"<div></div>")

    assert Named.__name__ == "Named"
    assert Named.__doc__ == "Doc."


def test_children_keyword_and_item_syntax_on_components(wyb, root_element):
    class CardProps(ParentProps):
        title: str

    @component
    def Card(props: CardProps):
        return html(t"<div><h2>{props.title}</h2>{props.children}</div>")

    a, b = html(t"<p>a</p>"), html(t"<p>b</p>")
    by_item = Card(title="Hi")[a, b]
    assert isinstance(by_item, VNode)
    assert by_item.props["children"] == [a, b]
    by_keyword = Card(title="Kw", children=[html(t"<p>c</p>")])
    wyb["reconciler"].render(html(t"<div>{by_item}{by_keyword}</div>"), root_element)
    assert texts(root_element.element) == ["Hi", "a", "b", "Kw", "c"]


def test_item_syntax_on_h_elements_sets_child_nodes(wyb, root_element):
    node = h("div", {"class_": "card"})[h("h2", None, "Title"), h("p", None, "Body")]
    assert isinstance(node, VNode)
    assert [c.tag for c in node.children] == ["h2", "p"]
    single = h("ul", None)[h("li", None, "only")]
    assert [c.tag for c in single.children] == ["li"]
    wyb["reconciler"].render(html(t"<div>{node}{single}</div>"), root_element)
    assert texts(root_element.element) == ["Title", "Body", "only"]
    card = elements(root_element.element.childNodes[0])[0]
    assert card.attributes["class"] == "card"


# ---------------------------------------------------------------------------
# Typed Props: validation and declaration
# ---------------------------------------------------------------------------


def test_missing_required_and_unknown_props_raise_in_dev_mode(wyb, dev_mode):
    class GreetingProps(Props):
        name: str
        excited: bool = prop(default=False)

    @component
    def Greeting(props: GreetingProps):
        return html(t"<p>{props.name}</p>")

    with pytest.raises(TypeError, match=r"missing required prop\(s\): name"):
        Greeting()
    with pytest.raises(TypeError, match=r"unexpected prop\(s\): bogus"):
        Greeting(name="x", bogus=1)
    # `key` and the declared fields are always accepted.
    assert isinstance(Greeting(name="x", excited=True, key="k"), VNode)


def test_component_without_props_rejects_props_but_accepts_key(wyb, dev_mode):
    @component
    def Plain():
        return html(t"<p>x</p>")

    with pytest.raises(TypeError, match="takes no props"):
        Plain(title="x")
    assert Plain(key="k").key == "k"


def test_prop_validation_is_skipped_in_production_mode(wyb):
    class GreetingProps(Props):
        name: str

    @component
    def Greeting(props: GreetingProps):
        return html(t"<p>{props.name}</p>")

    previous = _warnings.is_dev_mode()
    _warnings.set_dev_mode(False)
    try:
        assert isinstance(Greeting(bogus=1), VNode)
    finally:
        _warnings.set_dev_mode(previous)


def test_parameters_that_are_not_a_props_class_are_rejected(wyb, dev_mode):
    @component
    def Untyped(count):
        return html(t"<p>{count}</p>")

    @component
    def Keyword(*, props: Props):
        return html(t"<p>x</p>")

    @component
    def Two(a: Props, b: Props):
        return html(t"<p>x</p>")

    for comp in (Untyped, Keyword, Two):
        with pytest.raises(TypeError, match="must take no parameters or one parameter annotated with a Props subclass"):
            comp()


def test_base_props_annotation_accepts_only_key(wyb, root_element, dev_mode):
    seen: list[Props] = []

    @component
    def Raw(props: Props):
        seen.append(props)
        return html(t"<p>raw</p>")

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

    # A field specifier works on any plain field.
    class Counts(Props):
        count: int = prop(default=1)
        seen: list[int] = prop(default_factory=list)

    assert Counts().count == 1
    assert Counts().seen == []


def test_props_are_read_only(wyb, root_element):
    class P(Props):
        name: str = prop(default="x")
        tag: str = "t"

    errors: list[str] = []

    @component
    def Comp(props: P):
        for field in ("name", "tag"):
            try:
                setattr(props, field, "y")
            except AttributeError as exc:
                errors.append(str(exc))
        return html(t"<p>{props.name}</p>")

    wyb["reconciler"].render(Comp(), root_element)
    assert errors == ["Component props are read-only"] * 2


# ---------------------------------------------------------------------------
# Prop binding
# ---------------------------------------------------------------------------


def test_prop_reads_return_values_with_defaults(wyb, root_element):
    seen: dict[str, object] = {}

    class GreetingProps(Props):
        name: str = prop(default="world")
        excited: bool = False

    @component
    def Greeting(props: GreetingProps):
        # Constants can't change, so reading them at the top level is fine.
        seen["name"] = props.name
        seen["excited"] = props.excited
        return html(t"<p>Hello, {props.name}</p>")

    wyb["reconciler"].render(Greeting(), root_element)
    assert seen == {"name": "world", "excited": False}
    assert text(root_element.element) == "Hello, world"


def test_prop_default_factory_gives_each_instance_its_own_value(wyb, root_element):
    lists: list[list[str]] = []

    class TagsProps(Props):
        tags: list[str] = prop(default_factory=list)

    @component
    def Tags(props: TagsProps):
        value = props.tags
        value.append("x")
        lists.append(value)
        return html(t"<p>{len(value)}</p>")

    given = ["given"]
    wyb["reconciler"].render(html(t"<div><{Tags} /><{Tags} /><{Tags} tags={given} /></div>"), root_element)
    assert lists == [["x"], ["x"], ["given", "x"]]
    assert lists[0] is not lists[1]
    assert texts(root_element.element) == ["1", "1", "2"]


def test_plain_values_and_accessors_are_both_reactive_props(wyb, root_element):
    name, set_name = create_signal("Ada")

    class GreetingProps(Props):
        name: str
        suffix: str = ""

    @component
    def Greeting(props: GreetingProps):
        return html(t"<p>{props.name}{props.suffix}</p>")

    wyb["reconciler"].render(html(t'<{Greeting} name={name} suffix="!" />'), root_element)
    assert text(root_element.element) == "Ada!"
    set_name("Grace")
    flush()
    assert text(root_element.element) == "Grace!"


def test_compiled_expressions_are_reactive_props(wyb, root_element):
    first, set_first = create_signal("ada")

    class GreetingProps(Props):
        name: str

    @component
    def Greeting(props: GreetingProps):
        return html(t"<p>{props.name}</p>")

    # A dynamic expression in a component tag or a component call becomes a getter.
    wyb["reconciler"].render(
        html(t"<div><{Greeting} name={first().title()} />{Greeting(name=first().upper())}</div>"), root_element
    )
    assert texts(root_element.element) == ["Ada", "ADA"]
    set_first("grace")
    flush()
    assert texts(root_element.element) == ["Grace", "GRACE"]


def test_body_runs_once_even_when_props_change(wyb, root_element):
    count, set_count = create_signal(0)
    runs: list[int] = []

    class CounterProps(Props):
        value: int

    @component
    def Counter(props: CounterProps):
        runs.append(1)
        return html(t"<p>n={props.value}</p>")

    wyb["reconciler"].render(html(t"<{Counter} value={count()} />"), root_element)
    set_count(1)
    flush()
    set_count(2)
    flush()
    assert text(root_element.element) == "n=2"
    assert runs == [1]


def test_parent_rerender_patches_child_props_without_remount(wyb, root_element):
    label, set_label = create_signal("a")
    runs: list[int] = []

    class ChildProps(Props):
        text: str

    @component
    def Child(props: ChildProps):
        runs.append(1)
        return html(t"<span>{props.text}</span>")

    # The parent's hole re-renders a new VNode for Child with a plain value;
    # the mounted Child receives the new value through its live props.
    wyb["reconciler"].render(html(t"<div>{(lambda: Child(text=label()))}</div>"), root_element)
    assert texts(root_element.element) == ["a"]
    set_label("b")
    flush()
    assert texts(root_element.element) == ["b"]
    assert runs == [1]


def test_parent_updates_flow_into_every_field(wyb, root_element):
    n, set_n = create_signal(1)
    runs: list[int] = []
    seen: list[tuple[int, str]] = []
    reads: list[Callable[[], tuple[int, str]]] = []

    class ChildProps(Props):
        value: int
        mode: str = "plain"

    @component
    def Child(props: ChildProps):
        runs.append(1)
        create_effect(lambda: props.value, lambda v: seen.append((v, untrack(lambda: props.mode))))
        reads.append(lambda: untrack(lambda: (props.value, props.mode)))
        return html(t"<span>{props.value * 10}</span>")

    wyb["reconciler"].render(html(t"<div>{(lambda: Child(value=n(), mode=f'm{n()}'))}</div>"), root_element)
    flush()
    assert texts(root_element.element) == ["10"]
    set_n(2)
    flush()
    assert texts(root_element.element) == ["20"]
    assert runs == [1]
    assert seen == [(1, "m1"), (2, "m2")]
    # An untracked read sees the parent's latest values.
    assert reads[0]() == (2, "m2")


def test_omitted_prop_falls_back_to_default_after_parent_update(wyb, root_element):
    with_label, set_with_label = create_signal(True)

    class LabelProps(Props):
        label: str = "default"

    @component
    def Label(props: LabelProps):
        return html(t"<span>{props.label}</span>")

    wyb["reconciler"].render(
        html(t"<div>{(lambda: Label(label='given') if with_label() else Label())}</div>"), root_element
    )
    assert texts(root_element.element) == ["given"]
    set_with_label(False)
    flush()
    assert texts(root_element.element) == ["default"]


def test_omit_props_with_names_and_predicate_spreads_onto_elements(wyb, root_element):
    from wybthon.reactivity import omit

    cls, set_cls = create_signal("primary")

    class ButtonProps(Props):
        label: str
        class_: str | None = None
        id: str | None = None
        title: str | None = None

    rest_keys: list[list[str]] = []

    @component
    def Button(props: ButtonProps):
        rest = omit(props, "label")
        rest_keys.append(sorted(rest))
        no_title = omit(props, lambda key: key in ("label", "title"))
        rest_keys.append(sorted(no_title))
        return html(t"<button {no_title}>{props.label}</button>")

    wyb["reconciler"].render(Button(label="Go", class_=cls, id="b1", title="t"), root_element)
    assert rest_keys == [["class_", "id", "title"], ["class_", "id"]]
    btn = elements(root_element.element)[0]
    assert btn.attributes["id"] == "b1"
    assert btn.attributes["class"] == "primary"
    assert "title" not in btn.attributes
    set_cls("secondary")
    flush()
    assert btn.attributes["class"] == "secondary"


def test_untracked_prop_read_is_untracked(wyb, root_element):
    count, set_count = create_signal(0)
    runs: list[int] = []

    class PeekerProps(Props):
        value: int

    @component
    def Peeker(props: PeekerProps):
        def view():
            runs.append(1)
            return str(untrack(lambda: props.value))

        return html(t"<p>{view}</p>")

    wyb["reconciler"].render(html(t"<{Peeker} value={count()} />"), root_element)
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
        def click(event: Any) -> None:
            props.on_pick("picked")

        return html(t"<button onclick={click}>x</button>")

    wyb["reconciler"].render(Clicker(on_pick=calls.append), root_element)
    btn = elements(root_element.element)[0]
    wyb["kernel"]._backend.dispatch("click", btn)
    assert calls == ["picked"]


def test_zero_arg_callable_fields_are_never_called_on_read(wyb, root_element):
    calls: list[str] = []
    seen: list[Any] = []
    close = lambda: calls.append("closed")  # noqa: E731

    class DialogProps(Props):
        on_close: Callable[[], None] | None = None
        make_label: Callable[[], str] = lambda: "default"

    @component
    def Dialog(props: DialogProps):
        seen.append(props.on_close)
        seen.append(props.on_close)
        seen.append(props.make_label())

        def click() -> None:
            if props.on_close:
                props.on_close()

        return html(t"<button onclick={click}>close</button>")

    wyb["reconciler"].render(Dialog(on_close=close), root_element)
    assert seen == [close, close, "default"]
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
        return html(t"<p>{props.size}</p>")

    wyb["reconciler"].render(Comp(), root_element)
    assert seen == [3, None]
    assert texts(root_element.element) == ["3"]


def test_component_returning_string_list_or_none(wyb, root_element):
    @component
    def Text():
        return "plain"

    @component
    def Many():
        return [html(t"<span>a</span>"), html(t"<span>b</span>")]

    @component
    def Nothing():
        return None

    wyb["reconciler"].render(html(t"<div><{Text} /><{Many} /><{Nothing} /></div>"), root_element)
    assert texts(root_element.element) == ["plain", "a", "b"]


def test_component_returning_accessor_is_reactive(wyb, root_element):
    n, set_n = create_signal(1)

    @component
    def Value():
        return create_memo(lambda: f"v{n()}")

    wyb["reconciler"].render(html(t"<div><{Value} /></div>"), root_element)
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
        kids = children(lambda: props.children)
        assert isinstance(kids, ChildrenAccessor)
        counts.append(len(untrack(kids.to_array)))

        def items() -> list[VNode]:
            return [html(t"<li>{k}</li>") for k in kids.to_array()]

        return html(t"<ul>{items}</ul>")

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
        return html(t"<p>w</p>")

    wyb["reconciler"].render(html(t"<div>{Widget() if show() else None}</div>"), root_element)
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
        return html(t"<p>w</p>")

    wyb["reconciler"].render(html(t"<div>{Widget() if show() else None}<span>{unmounts()}</span></div>"), root_element)
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
        return html(t"<p>w</p>")

    wyb["reconciler"].render(html(t"<div>{Watcher() if show() else None}</div>"), root_element)
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
        return html(t"<p>mounted</p>")

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
        return html(t"<p>w</p>")

    wyb["reconciler"].render(html(t"<div>{Watcher() if show() else None}</div>"), root_element)
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


def test_top_level_read_of_a_reactive_prop_warns_in_dev_mode(wyb, root_element, capsys, dev_mode):
    _warnings._reset_warning_dedupe()
    name, _ = create_signal("x")

    class BadProps(Props):
        name: str

    @component
    def Bad(props: BadProps):
        value = props.name
        return html(t"<p>{value}</p>")

    wyb["reconciler"].render(html(t"<{Bad} name={name()} />"), root_element)
    err = capsys.readouterr().err
    assert "Warning" in err
    assert "Bad" in err
    assert "name" in err


def test_top_level_read_of_a_constant_prop_does_not_warn(wyb, root_element, capsys, dev_mode):
    _warnings._reset_warning_dedupe()

    class FineProps(Props):
        name: str

    @component
    def Fine(props: FineProps):
        value = props.name
        return html(t"<p>{value}</p>")

    wyb["reconciler"].render(html(t'<div><{Fine} name="x" />{Fine(name="y")}</div>'), root_element)
    assert texts(root_element.element) == ["x", "y"]
    assert capsys.readouterr().err == ""


def test_top_level_read_does_not_warn_when_untracked_or_a_callback(wyb, root_element, capsys, dev_mode):
    _warnings._reset_warning_dedupe()
    name, _ = create_signal("x")

    class FineProps(Props):
        name: str
        on_done: Callable[[], None] | None = None

    @component
    def Fine(props: FineProps):
        value = untrack(lambda: props.name)
        _ = props.on_done
        return html(t"<p>{value}</p>")

    done = lambda: None  # noqa: E731
    wyb["reconciler"].render(html(t"<{Fine} name={name()} on_done={done} />"), root_element)
    assert texts(root_element.element) == ["x"]
    assert capsys.readouterr().err == ""


def test_nested_components_and_keyed_remount(wyb, root_element):
    key, set_key = create_signal("a")
    mounted: list[str] = []

    class LeafProps(Props):
        tag: str

    @component
    def Leaf(props: LeafProps):
        tag = untrack(lambda: props.tag)
        mounted.append(tag)
        on_cleanup(lambda: mounted.append(f"-{tag}"))
        return html(t"<span>{props.tag}</span>")

    @component
    def Tree():
        return html(t"<div>{(lambda: Leaf(tag=key(), key=key()))}</div>")

    wyb["reconciler"].render(Tree(), root_element)
    set_key("b")
    flush()
    assert texts(root_element.element) == ["b"]
    assert mounted == ["a", "-a", "b"]


def test_same_key_patches_and_new_key_remounts(wyb, root_element):
    state, set_state = create_signal(("k1", "a"))
    mounted: list[str] = []

    class LeafProps(Props):
        text: str

    @component
    def Leaf(props: LeafProps):
        mounted.append(untrack(lambda: props.text))
        return html(t"<span>{props.text}</span>")

    wyb["reconciler"].render(html(t"<div>{(lambda: Leaf(text=state()[1], key=state()[0]))}</div>"), root_element)
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
        name: str
        copies: int = prop(default=2)

    @component
    def Greeting(props: GreetingProps):
        return html(t"<p>{props.name * props.copies}</p>")

    wyb["reconciler"].render(Greeting(name=Model().name), root_element)
    assert texts(root_element.element) == ["AdaAda"]
    set_name("Grace")
    flush()
    assert texts(root_element.element) == ["GraceGrace"]


def test_string_annotation_resolves_to_module_level_props(wyb, root_element):
    @component
    def Card(props: "_ModuleCardProps"):
        return html(t"<p>{props.title}</p>")

    wyb["reconciler"].render(Card(title="bound"), root_element)
    assert texts(root_element.element) == ["bound"]


class _ModuleCardProps(Props):
    title: str
