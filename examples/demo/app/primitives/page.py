from wybthon import (
    For,
    Ref,
    button,
    component,
    create_portal,
    create_signal,
    div,
    dynamic,
    h,
    h2,
    h3,
    memo,
    on_mount,
    p,
    span,
)

_child_render_count = [0]


@component
def _ExpensiveChild(label=None):
    _child_render_count[0] += 1
    runs = _child_render_count[0]
    return p(dynamic(lambda: f"Child rendered {runs} time(s). label={label()}"))


MemoChild = memo(_ExpensiveChild)


@component
def MemoDemo():
    count, set_count = create_signal(0)

    return div(
        h3("memo - Memoized Component"),
        p("Parent render count trigger: ", count),
        button("Re-render parent", on_click=lambda e: set_count(count() + 1)),
        h(MemoChild, {"label": "stable"}),
        p(
            "Child only renders once because its 'label' prop never changes.",
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
                children=lambda item, idx: p(dynamic(lambda: f"  {item()}"), key=idx()),
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
            p("Core reactive primitives: memo, signals, on_mount, and create_portal."),
            class_="page-header",
        ),
        h(MemoDemo, {}),
        h(TodoDemo, {}),
        h(MountDemo, {}),
        h(PortalDemo, {}),
        class_="page",
    )
