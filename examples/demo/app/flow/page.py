from wybthon import (
    Dynamic,
    For,
    Index,
    Match,
    Show,
    Switch,
    button,
    component,
    create_signal,
    div,
    dynamic,
    h,
    h2,
    h3,
    li,
    p,
    ul,
)


@component
def ShowDemo():
    visible, set_visible = create_signal(True)
    count, set_count = create_signal(0)

    return div(
        h3("Show - Conditional Rendering"),
        p(
            "Show uses keyed conditional rendering. When truthiness changes, "
            "the previous branch scope is disposed and a new scope is created."
        ),
        div(
            button("Toggle", on_click=lambda e: set_visible(not visible())),
            button("+1", on_click=lambda e: set_count(count() + 1)),
            style={"display": "flex", "gap": "8px"},
        ),
        Show(
            when=visible,
            children=lambda: p(dynamic(lambda: f"Visible! Count is {count()}")),
            fallback=lambda: p("Hidden (fallback shown)", style={"color": "var(--text-3)"}),
        ),
        class_="demo-section",
    )


@component
def ForDemo():
    items, set_items = create_signal(["Alpha", "Beta", "Gamma"])
    next_id, set_next_id = create_signal(4)

    def add_item(e):
        new_name = f"Item-{next_id()}"
        set_items([*items(), new_name])
        set_next_id(next_id() + 1)

    def remove_last(e):
        cur = items()
        if cur:
            set_items(cur[:-1])

    return div(
        h3("For - Keyed List Rendering"),
        p(
            "For maintains per-item reactive scopes keyed by identity. "
            "The mapping callback runs once per unique item and receives "
            "signal-backed item() and index() getters."
        ),
        div(
            button("Add item", on_click=add_item),
            button("Remove last", on_click=remove_last),
            style={"display": "flex", "gap": "8px"},
        ),
        ul(
            For(
                each=items,
                children=lambda item, idx: li(dynamic(lambda: f"{idx()}: {item()}"), key=idx()),
            ),
        ),
        class_="demo-section",
    )


@component
def SwitchDemo():
    status, set_status = create_signal("idle")

    def cycle(e):
        cur = status()
        nxt = {"idle": "loading", "loading": "error", "error": "ready", "ready": "idle"}
        set_status(nxt.get(cur, "idle"))

    return div(
        h3("Switch / Match - Multi-Branch"),
        p("Current status: ", status),
        button("Cycle status", on_click=cycle),
        Switch(
            Match(when=lambda: status() == "loading", children=lambda: p("Loading...", style={"color": "orange"})),
            Match(when=lambda: status() == "error", children=lambda: p("Error!", style={"color": "red"})),
            Match(when=lambda: status() == "ready", children=lambda: p("Ready.", style={"color": "green"})),
            fallback=lambda: p("Idle - click to start", style={"color": "var(--text-3)"}),
        ),
        class_="demo-section",
    )


@component
def DynamicDemo():
    level, set_level = create_signal("h3")

    def cycle(e):
        cur = level()
        nxt = {"h3": "h2", "h2": "h1", "h1": "p", "p": "h3"}
        set_level(nxt.get(cur, "h3"))

    return div(
        h3("Dynamic - Dynamic Component"),
        p("Current tag: ", dynamic(lambda: f"<{level()}>")),
        button("Cycle tag", on_click=cycle),
        Dynamic(component=lambda: level(), children=["Dynamic content!"]),
        class_="demo-section",
    )


@component
def IndexDemo():
    items, set_items = create_signal(["First", "Second", "Third"])

    def shuffle(e):
        cur = list(items())
        cur.reverse()
        set_items(cur)

    return div(
        h3("Index - Index-Stable Rendering"),
        p(
            "Index maintains per-index reactive scopes. Each slot has a "
            "signal-backed item() getter that updates when the value at "
            "that position changes."
        ),
        button("Reverse", on_click=shuffle),
        ul(
            Index(
                each=items,
                children=lambda item, idx: li(dynamic(lambda: f"[{idx}] {item()}")),
            ),
        ),
        class_="demo-section",
    )


@component
def Page():
    return div(
        div(
            h2("Flow Control"),
            p(
                "Reactive flow control components: Show, For, Index, Switch/Match, "
                "and Dynamic. Each creates an isolated reactive scope."
            ),
            class_="page-header",
        ),
        h(ShowDemo, {}),
        h(ForDemo, {}),
        h(SwitchDemo, {}),
        h(IndexDemo, {}),
        h(DynamicDemo, {}),
        class_="page",
    )
