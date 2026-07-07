from wybthon import (
    For,
    Ref,
    button,
    component,
    create_memo,
    create_portal,
    create_signal,
    div,
    dynamic,
    h,
    h2,
    h3,
    on_mount,
    p,
    span,
)

_memo_run_count = [0]


@component
def MemoDemo():
    count, set_count = create_signal(0)

    def compute_parity():
        _memo_run_count[0] += 1
        return "even" if count() % 2 == 0 else "odd"

    parity = create_memo(compute_parity)

    def memo_runs():
        parity()  # subscribe so this hole re-runs when the memo recomputes
        return f"Memo has computed {_memo_run_count[0]} time(s)."

    return div(
        h3("create_memo - Derived Value"),
        p("Count: ", count),
        button("Increment", on_click=lambda e: set_count(count() + 1)),
        p("Parity (memoized): ", parity),
        p(dynamic(memo_runs)),
        p(
            "The memo recomputes lazily when count changes, and downstream "
            "consumers only re-run when its value actually changes.",
            style={"color": "var(--text-3)", "fontSize": "0.85rem"},
        ),
        class_="demo-section",
    )


@component
def TodoDemo():
    items, set_items = create_signal([])
    next_id, set_next_id = create_signal(1)

    def add_item(e):
        set_items([*items(), f"Item {next_id()}"])
        set_next_id(next_id() + 1)

    def clear_items(e):
        set_items([])

    return div(
        h3("Signal-based Todo List"),
        p(dynamic(lambda: f"Items: {len(items())}")),
        div(
            button("Add item", on_click=add_item),
            button("Clear all", on_click=clear_items),
        ),
        div(
            For(
                each=items,
                children=lambda item, idx: p(item),
            ),
        ),
        class_="demo-section",
    )


@component
def MountDemo():
    message, set_message = create_signal("(waiting for mount...)")

    on_mount(lambda: set_message("on_mount callback ran successfully!"))

    return div(
        h3("on_mount"),
        p(message),
        class_="demo-section",
    )


@component
def PortalDemo():
    show, set_show = create_signal(False)
    ref = Ref()

    def maybe_portal():
        target_el = ref.current
        if not show() or target_el is None:
            return span("")
        return create_portal(
            div(
                div(
                    p("This content is rendered via create_portal into the target below."),
                    button("Close", on_click=lambda e: set_show(False)),
                    style={
                        "padding": "12px",
                        "background": "var(--primary-light)",
                        "border": "1px solid var(--primary)",
                        "borderRadius": "var(--radius)",
                    },
                ),
            ),
            target_el,
        )

    return div(
        h3("create_portal"),
        button("Toggle portal", on_click=lambda e: set_show(not show())),
        p(
            "Portal target container:",
            style={"marginTop": "8px", "color": "var(--text-3)"},
        ),
        h(
            "div",
            {
                "ref": ref,
                "style": {
                    "minHeight": "40px",
                    "border": "1px dashed var(--border-2)",
                    "borderRadius": "var(--radius)",
                    "padding": "8px",
                    "marginTop": "4px",
                },
            },
        ),
        dynamic(maybe_portal),
        class_="demo-section",
    )


@component
def Page():
    return div(
        div(
            h2("Primitives"),
            p("Core reactive primitives: create_memo, signals, on_mount, and create_portal."),
            class_="page-header",
        ),
        h(MemoDemo, {}),
        h(TodoDemo, {}),
        h(MountDemo, {}),
        h(PortalDemo, {}),
        class_="page",
    )
