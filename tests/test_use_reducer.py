"""Tests for use_reducer hook."""

import time

from conftest import collect_texts

import wybthon as _wybthon_pkg  # noqa: F401


def _counter_reducer(state, action):
    if action == "increment":
        return state + 1
    if action == "decrement":
        return state - 1
    if action == "reset":
        return 0
    return state


def test_use_reducer_initial_render(wyb, root_element):
    vdom = wyb["vdom"]
    hooks = wyb["hooks"]

    render_log = []

    def Counter(props):
        count, dispatch = hooks.use_reducer(_counter_reducer, 0)
        render_log.append(count)
        return vdom.h("p", {}, f"Count: {count}")

    vdom.render(vdom.h(Counter, {}), root_element)

    assert render_log == [0]
    assert "Count: 0" in collect_texts(root_element.element)


def test_use_reducer_dispatch(wyb, root_element):
    vdom = wyb["vdom"]
    hooks = wyb["hooks"]

    dispatch_ref = [None]
    render_log = []

    def Counter(props):
        count, dispatch = hooks.use_reducer(_counter_reducer, 0)
        dispatch_ref[0] = dispatch
        render_log.append(count)
        return vdom.h("p", {}, f"Count: {count}")

    vdom.render(vdom.h(Counter, {}), root_element)
    assert render_log == [0]

    dispatch_ref[0]("increment")
    time.sleep(0.05)
    assert render_log[-1] == 1

    dispatch_ref[0]("increment")
    time.sleep(0.05)
    assert render_log[-1] == 2

    dispatch_ref[0]("decrement")
    time.sleep(0.05)
    assert render_log[-1] == 1

    dispatch_ref[0]("reset")
    time.sleep(0.05)
    assert render_log[-1] == 0


def test_use_reducer_with_init(wyb, root_element):
    vdom = wyb["vdom"]
    hooks = wyb["hooks"]

    init_calls = [0]

    def init_fn(arg):
        init_calls[0] += 1
        return {"count": arg, "step": 1}

    def reducer(state, action):
        if action == "step":
            return {**state, "count": state["count"] + state["step"]}
        return state

    dispatch_ref = [None]
    state_log = []

    def StepCounter(props):
        state, dispatch = hooks.use_reducer(reducer, 10, init=init_fn)
        dispatch_ref[0] = dispatch
        state_log.append(state)
        return vdom.h("p", {}, f"count={state['count']}")

    vdom.render(vdom.h(StepCounter, {}), root_element)

    assert init_calls[0] == 1
    assert state_log[0] == {"count": 10, "step": 1}
    assert "count=10" in collect_texts(root_element.element)

    dispatch_ref[0]("step")
    time.sleep(0.05)
    assert state_log[-1] == {"count": 11, "step": 1}


def test_use_reducer_dispatch_stable_identity(wyb, root_element):
    """The dispatch function should be the same reference across renders."""
    vdom = wyb["vdom"]
    hooks = wyb["hooks"]

    dispatch_ids = []
    setter_ref = [None]

    def MyComp(props):
        _count, dispatch = hooks.use_reducer(_counter_reducer, 0)
        # Also have a useState to trigger re-renders independently
        val, setter = hooks.use_state(0)
        setter_ref[0] = setter
        dispatch_ids.append(id(dispatch))
        return vdom.h("p", {}, "ok")

    vdom.render(vdom.h(MyComp, {}), root_element)

    setter_ref[0](1)
    time.sleep(0.05)

    assert len(dispatch_ids) == 2
    assert dispatch_ids[0] == dispatch_ids[1]
