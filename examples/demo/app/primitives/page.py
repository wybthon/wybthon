from wybthon import (
    button,
    component,
    create_portal,
    div,
    h,
    h2,
    h3,
    hr,
    memo,
    p,
    span,
    use_layout_effect,
    use_reducer,
    use_ref,
    use_state,
)

# ---------------------------------------------------------------------------
# 1) memo – skips re-renders when props are unchanged
# ---------------------------------------------------------------------------

_child_render_count = [0]


@component
def _ExpensiveChild(label=None):
    _child_render_count[0] += 1
    return p(f"Child rendered {_child_render_count[0]} time(s). label={label}")


MemoChild = memo(_ExpensiveChild)


@component
def MemoDemo():
    count, set_count = use_state(0)
    return div(
        h3("memo – Memoized Component"),
        p(f"Parent render count trigger: {count}"),
        button("Re-render parent", on_click=lambda e: set_count(lambda c: c + 1)),
        h(MemoChild, {"label": "stable"}),
        p("(Child only renders once because its 'label' prop never changes.)", style={"color": "#888"}),
    )


# ---------------------------------------------------------------------------
# 2) use_reducer – complex state management
# ---------------------------------------------------------------------------


def _todo_reducer(state, action):
    kind = action.get("type") if isinstance(action, dict) else action
    if kind == "add":
        return {**state, "items": state["items"] + [action["text"]], "next_id": state["next_id"] + 1}
    if kind == "clear":
        return {**state, "items": []}
    return state


@component
def ReducerDemo():
    state, dispatch = use_reducer(_todo_reducer, {"items": [], "next_id": 1})
    return div(
        h3("use_reducer – Todo List"),
        p(f"Items: {len(state['items'])}"),
        button("Add item", on_click=lambda e: dispatch({"type": "add", "text": f"Item {state['next_id']}"})),
        " ",
        button("Clear all", on_click=lambda e: dispatch({"type": "clear"})),
        div(*[p(f"• {item}") for item in state["items"]]),
    )


# ---------------------------------------------------------------------------
# 3) use_layout_effect – synchronous DOM effect
# ---------------------------------------------------------------------------


@component
def LayoutEffectDemo():
    message, set_message = use_state("(measuring...)")

    def measure():
        set_message("Layout effect ran synchronously after mount!")

    use_layout_effect(measure, [])

    return div(
        h3("use_layout_effect"),
        p(message),
    )


# ---------------------------------------------------------------------------
# 4) create_portal – render into a different container
# ---------------------------------------------------------------------------


@component
def PortalDemo():
    show, set_show = use_state(False)
    ref = use_ref(None)

    portal_content = div(
        div(
            p("This content is rendered via create_portal into the portal target below."),
            button("Close", on_click=lambda e: set_show(False)),
            style={"padding": "12px", "background": "#e0f0ff", "border": "1px solid #0090d9", "borderRadius": "6px"},
        ),
    )

    target_el = ref.current
    return div(
        h3("create_portal"),
        button("Toggle portal", on_click=lambda e: set_show(lambda s: not s)),
        p("Portal target container:", style={"marginTop": "8px", "color": "#888"}),
        h(
            "div",
            {"ref": ref, "style": {"minHeight": "40px", "border": "1px dashed #ccc", "padding": "8px"}},
        ),
        create_portal(portal_content, target_el) if (show and target_el is not None) else span(""),
    )


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------


@component
def Page():
    return div(
        h2("New Primitives"),
        h(MemoDemo, {}),
        hr(),
        h(ReducerDemo, {}),
        hr(),
        h(LayoutEffectDemo, {}),
        hr(),
        h(PortalDemo, {}),
    )
