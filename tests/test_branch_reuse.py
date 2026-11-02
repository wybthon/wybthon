"""Reusable node slots keep their values across branch lifetimes."""

from collections.abc import Callable
from typing import Any, NamedTuple

import pytest

from wybthon import (
    For,
    Match,
    ParentProps,
    Show,
    Switch,
    component,
    create_effect,
    create_signal,
    flush,
    h,
    hole,
    html,
    on_cleanup,
)
from wybthon.testing import cleanup, fire, render


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    cleanup()


@pytest.mark.parametrize("kind", ["text", "attribute", "component_tag", "component_call", "inline", "children"])
@pytest.mark.parametrize("fallback", [False, True])
def test_show_reuses_compiled_node_slots(kind, fallback):
    visible, set_visible = create_signal(not fallback)
    value, set_value = create_signal("hello")

    @component
    def Child():
        return html(t"<strong>{value()}</strong>")

    @component
    def Wrapper(props: ParentProps):
        return html(t"<article>{props.children}</article>")

    @component
    def App():
        if kind == "attribute":
            node = html(t"<b title={value()}>{value()}</b>")
        elif kind == "component_tag":
            node = html(t"<div><{Child} /></div>")
        elif kind == "component_call":
            node = html(t"<div>{Child()}</div>")
        elif kind == "inline":
            if fallback:
                return html(t"<section>{Show(visible, html(t'<i>hidden</i>'), html(t'<b>{value()}</b>'))}</section>")
            return html(t"<section>{Show(visible, html(t'<b>{value()}</b>'), html(t'<i>hidden</i>'))}</section>")
        elif kind == "children":
            node = Wrapper()[html(t"<b>{value()}</b>")]
        else:
            node = html(t"<b>{value()}</b>")
        hidden = html(t"<i>hidden</i>")
        selected = Show(visible, hidden, node) if fallback else Show(visible, node, hidden)
        return selected

    with render(App()) as screen:
        assert screen.text() == "hello"
        for index in range(3):
            set_value(f"shown {index}")
            flush()
            assert screen.text() == f"shown {index}"
            set_visible(fallback)
            flush()
            assert screen.text() == "hidden"
            set_value(f"hidden {index}")
            flush()
            assert screen.text() == "hidden"
            set_visible(not fallback)
            flush()
            assert screen.text() == f"hidden {index}"


def test_switch_reuses_compiled_fallback_across_selections():
    selected, set_selected = create_signal(False)
    value, set_value = create_signal("hello")
    fallback = html(t"<b>{value()}</b>")
    view = Switch(Match(selected, html(t"<i>selected</i>")), fallback=fallback)

    with render(view) as screen:
        assert screen.text() == "hello"
        for index in range(3):
            set_value(f"shown {index}")
            flush()
            assert screen.text() == f"shown {index}"
            set_selected(True)
            flush()
            assert screen.text() == "selected"
            set_value(f"hidden {index}")
            flush()
            assert screen.text() == "selected"
            set_selected(False)
            flush()
            assert screen.text() == f"hidden {index}"
    assert screen.container.childNodes == []
    set_value("after cleanup")
    flush()
    assert screen.text() == ""


def test_hole_reuses_stored_compiled_node_across_selections():
    visible, set_visible = create_signal(True)
    value, set_value = create_signal("hello")
    stored = html(t"<b>{value()}</b>")

    with render(hole(lambda: stored if visible() else None)) as screen:
        assert screen.text() == "hello"
        for index in range(3):
            element = screen.get_by_text("hello" if index == 0 else f"hidden {index - 1}")
            set_value(f"shown {index}")
            flush()
            assert screen.text() == f"shown {index}"
            assert screen.get_by_text(f"shown {index}") is element
            set_visible(False)
            flush()
            assert screen.text() == ""
            set_value(f"hidden {index}")
            flush()
            assert screen.text() == ""
            set_visible(True)
            flush()
            assert screen.text() == f"hidden {index}"
    assert screen.container.childNodes == []
    set_value("after cleanup")
    flush()
    assert screen.text() == ""


@pytest.mark.parametrize("kind", ["fragment", "list", "tuple", "nested_list", "programmatic", "nested_show"])
def test_show_reuses_nested_node_values(kind):
    visible, set_visible = create_signal(True)
    value = "hello"
    child = html(t"<b>{value}</b>")
    if kind == "fragment":
        node = html(t"<i>before</i>{child}<i>after</i>")
    elif kind == "list":
        node = [child]
    elif kind == "tuple":
        node = (child,)
    elif kind == "nested_list":
        nodes = [[child]]
        node = html(t"<div>{nodes}</div>")
    elif kind == "programmatic":
        node = h("div", None, child)
    else:
        node = Show(True, child)
    expected = "beforehelloafter" if kind == "fragment" else "hello"
    with render(Show(visible, node)) as screen:
        for _ in range(3):
            assert screen.text() == expected
            set_visible(False)
            flush()
            assert screen.text() == ""
            set_visible(True)
            flush()
            assert screen.text() == expected


@pytest.mark.parametrize("kind", ["node", "list", "tuple", "nested_list", "nested_tuple"])
@pytest.mark.parametrize("container", ["direct", "list", "tuple", "nested_list"])
@pytest.mark.parametrize("field", ["children", "body"])
def test_show_reuses_a_component_that_selects_its_child(kind, container, field):
    visible, set_visible = create_signal(True)
    value = "hello"
    child = html(t"<b>{value}</b>")
    child.key = "child"
    children = {
        "node": child,
        "list": [child],
        "tuple": (child,),
        "nested_list": [[child]],
        "nested_tuple": ((child,),),
    }

    class FirstProps(ParentProps):
        body: Any = None

    @component
    def First(props: FirstProps):
        selected = props.children if field == "children" else props.body
        while isinstance(selected, (list, tuple)):
            selected = selected[0]
        assert selected.key == "child"
        return selected

    node = First(**{field: children[kind]})
    slots = {"direct": node, "list": [node], "tuple": (node,), "nested_list": [[node]]}
    with render(Show(visible, slots[container])) as screen:
        for _ in range(3):
            assert screen.text() == "hello"
            set_visible(False)
            flush()
            assert screen.text() == ""
            set_visible(True)
            flush()
            assert screen.text() == "hello"


@pytest.mark.parametrize("kind", ["list", "cyclic_list", "tuple_subclass", "shared_sequences"])
def test_copying_node_slots_preserves_model_and_callback_identity(kind):
    visible, set_visible = create_signal(True)

    class Model(NamedTuple):
        label: str

    model: Any = Model("model") if kind == "tuple_subclass" else ["model", {"value": 1}]
    if kind == "cyclic_list":
        model.append(model)
    elif kind == "shared_sequences":
        for _ in range(20):
            model = [model, model]
    value = "hello"

    class ChildProps(ParentProps):
        data: object
        callback: Callable[[], None]

    def callback():
        raise AssertionError("Copying a callback must not evaluate it")

    @component
    def Child(props: ChildProps):
        assert props.data is model
        assert props.callback is callback
        return props.children

    child = html(t"<b>{value}</b>")
    node = html(t"<div><{Child} data={model} callback={callback} children={child} /></div>")
    with render(Show(visible, node)) as screen:
        for _ in range(3):
            assert screen.text() == "hello"
            set_visible(False)
            flush()
            set_visible(True)
            flush()
            assert screen.text() == "hello"


def test_copying_node_slots_tolerates_ignored_metadata_cycles():
    visible, set_visible = create_signal(True)
    value = "hello"

    def View(props):
        return html(t"<b>{value}</b>")

    node = h(View, {})
    node.props["metadata"] = node
    with render(Show(visible, node)) as screen:
        for _ in range(3):
            assert screen.text() == "hello"
            set_visible(False)
            flush()
            set_visible(True)
            flush()
            assert screen.text() == "hello"


def test_copying_nested_regions_takes_linear_node_allocations(monkeypatch):
    from wybthon.vnode import VNode

    depth = 20
    view = html(t"<b>hello</b>")
    for _ in range(depth):
        view = Show(True, view)
    allocated = 0
    original = VNode.__init__

    def counted(self, *args, **kwargs):
        nonlocal allocated
        allocated += 1
        original(self, *args, **kwargs)

    monkeypatch.setattr(VNode, "__init__", counted)
    with render(view) as screen:
        assert screen.text() == "hello"
        assert allocated <= depth * 3 + 10


def test_copying_a_list_region_preserves_row_data_identity():
    visible, set_visible = create_signal(True)
    item = html(t"<b>data</b>")
    seen = []

    def row(value, index):
        seen.append(value)
        return html(t"<i>row</i>")

    with render(Show(visible, For([item], row))) as screen:
        for index in range(3):
            assert screen.text() == "row"
            assert len(seen) == index + 1
            assert seen[-1] is item
            set_visible(False)
            flush()
            set_visible(True)
            flush()


@pytest.mark.parametrize("kind", ["show", "switch", "list_fallback"])
def test_node_slot_lifetimes_dispose_effects_and_handlers(kind):
    visible, set_visible = create_signal(True)
    value, set_value = create_signal("hello")
    mounted, disposed, effects, clicks = [], [], [], []

    @component
    def Child():
        token = len(mounted)
        mounted.append(token)
        on_cleanup(lambda: disposed.append(token))
        create_effect(value, lambda current: effects.append((token, current)))
        return html(t"<button onclick={(lambda: clicks.append(token))}>{value()}</button>")

    node = html(t"<div><{Child} /></div>")
    if kind == "show":
        view = Show(visible, node)
    elif kind == "switch":
        view = Switch(Match(visible, node))
    else:
        rows = lambda: [] if visible() else [1]  # noqa: E731
        view = For(rows, lambda item, index: None, fallback=node)
    with render(view) as screen:
        assert effects == [(0, "hello")]
        for index in range(3):
            button = screen.get_by_role("button")
            fire.click(button)
            assert clicks == list(range(index + 1))
            set_visible(False)
            flush()
            assert disposed == list(range(index + 1))
            fire.click(button)
            assert clicks == list(range(index + 1))
            previous = list(effects)
            set_value(f"later {index}")
            flush()
            assert effects == previous
            set_visible(True)
            flush()
            assert screen.text() == f"later {index}"
            assert effects[-1] == (index + 1, f"later {index}")
    assert disposed == list(range(4))
    assert screen.container.childNodes == []
    screen.unmount()
    cleanup()
    previous = list(effects)
    set_value("after cleanup")
    flush()
    assert effects == previous
    assert disposed == list(range(4))


def test_factory_output_still_releases_interpolation_values():
    visible, set_visible = create_signal(True)
    nodes: list[Any] = []

    def branch():
        value = "hello"
        node = html(t"<b>{value}</b>")
        nodes.append(node)
        return node

    with render(Show(visible, branch)) as screen:
        assert screen.text() == "hello"
        assert nodes[0].children == ()
        set_visible(False)
        flush()
        set_visible(True)
        flush()
        assert screen.text() == "hello"
        assert len(nodes) == 2
        assert nodes[1].children == ()
