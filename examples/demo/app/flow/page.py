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

    def render():
        return div(
            h3("Show - Conditional Rendering"),
            p("Show creates its own reactive scope. Toggling visibility only re-renders the Show subtree."),
            div(
                button("Toggle", on_click=lambda e: set_visible(not visible())),
                button("+1", on_click=lambda e: set_count(count() + 1)),
                style={"display": "flex", "gap": "8px"},
            ),
            Show(
                when=visible,
                children=lambda: p(f"Visible! Count is {count()}"),
                fallback=lambda: p("Hidden (fallback shown)", style={"color": "var(--text-3)"}),
            ),
            class_name="demo-section",
        )

    return render


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

    def render():
        return div(
            h3("For - Keyed List Rendering"),
            p("For takes a getter and a mapping callback. Each item receives a reactive item() getter."),
            div(
                button("Add item", on_click=add_item),
                button("Remove last", on_click=remove_last),
                style={"display": "flex", "gap": "8px"},
            ),
            ul(
                For(
                    each=items,
                    children=lambda item, idx: li(f"{idx()}: {item()}", key=idx()),
                ),
            ),
            class_name="demo-section",
        )

    return render


@component
def SwitchDemo():
    status, set_status = create_signal("idle")

    def cycle(e):
        cur = status()
        nxt = {"idle": "loading", "loading": "error", "error": "ready", "ready": "idle"}
        set_status(nxt.get(cur, "idle"))

    def render():
        return div(
            h3("Switch / Match - Multi-Branch"),
            p(f"Current status: {status()}"),
            button("Cycle status", on_click=cycle),
            Switch(
                Match(when=lambda: status() == "loading", children=lambda: p("Loading...", style={"color": "orange"})),
                Match(when=lambda: status() == "error", children=lambda: p("Error!", style={"color": "red"})),
                Match(when=lambda: status() == "ready", children=lambda: p("Ready.", style={"color": "green"})),
                fallback=lambda: p("Idle - click to start", style={"color": "var(--text-3)"}),
            ),
            class_name="demo-section",
        )

    return render


@component
def DynamicDemo():
    level, set_level = create_signal("h3")

    def cycle(e):
        cur = level()
        nxt = {"h3": "h2", "h2": "h1", "h1": "p", "p": "h3"}
        set_level(nxt.get(cur, "h3"))

    def render():
        return div(
            h3("Dynamic - Dynamic Component"),
            p(f"Current tag: <{level()}>"),
            button("Cycle tag", on_click=cycle),
            Dynamic(component=lambda: level(), children=["Dynamic content!"]),
            class_name="demo-section",
        )

    return render


@component
def IndexDemo():
    items, set_items = create_signal(["First", "Second", "Third"])

    def shuffle(e):
        cur = list(items())
        cur.reverse()
        set_items(cur)

    def render():
        return div(
            h3("Index - Index-Stable Rendering"),
            p("Index gives a stable item() getter per index position."),
            button("Reverse", on_click=shuffle),
            ul(
                Index(
                    each=items,
                    children=lambda item, idx: li(f"[{idx}] {item()}"),
                ),
            ),
            class_name="demo-section",
        )

    return render


@component
def Page():
    return div(
        div(
            h2("Flow Control"),
            p(
                "Reactive flow control components: Show, For, Index, Switch/Match, "
                "and Dynamic. Each creates an isolated reactive scope."
            ),
            class_name="page-header",
        ),
        h(ShowDemo, {}),
        h(ForDemo, {}),
        h(SwitchDemo, {}),
        h(IndexDemo, {}),
        h(DynamicDemo, {}),
        class_name="page",
    )
