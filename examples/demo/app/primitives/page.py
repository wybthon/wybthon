from wybthon import (
    Ref,
    button,
    component,
    create_portal,
    create_signal,
    div,
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
    return p(f"Child rendered {_child_render_count[0]} time(s). label={label()}")


MemoChild = memo(_ExpensiveChild)


@component
def MemoDemo():
    count, set_count = create_signal(0)

    def render():
        return div(
            h3("memo - Memoized Component"),
            p(f"Parent render count trigger: {count()}"),
            button("Re-render parent", on_click=lambda e: set_count(count() + 1)),
            h(MemoChild, {"label": "stable"}),
            p(
                "Child only renders once because its 'label' prop never changes.",
                style={"color": "var(--text-3)", "fontSize": "0.85rem"},
            ),
            class_name="demo-section",
        )

    return render


@component
def TodoDemo():
    items, set_items = create_signal([])
    next_id, set_next_id = create_signal(1)

    def add_item(e):
        set_items([*items(), f"Item {next_id()}"])
        set_next_id(next_id() + 1)

    def clear_items(e):
        set_items([])

    def render():
        return div(
            h3("Signal-based Todo List"),
            p(f"Items: {len(items())}"),
            div(
                button("Add item", on_click=add_item),
                button("Clear all", on_click=clear_items),
            ),
            div(*[p(f"  {item}") for item in items()]),
            class_name="demo-section",
        )

    return render


@component
def MountDemo():
    message, set_message = create_signal("(waiting for mount...)")

    on_mount(lambda: set_message("on_mount callback ran successfully!"))

    def render():
        return div(
            h3("on_mount"),
            p(message()),
            class_name="demo-section",
        )

    return render


@component
def PortalDemo():
    show, set_show = create_signal(False)
    ref = Ref()

    def render():
        target_el = ref.current

        portal_content = div(
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
            create_portal(portal_content, target_el) if (show() and target_el is not None) else span(""),
            class_name="demo-section",
        )

    return render


@component
def Page():
    return div(
        div(
            h2("Primitives"),
            p("Core reactive primitives: memo, signals, on_mount, and create_portal."),
            class_name="page-header",
        ),
        h(MemoDemo, {}),
        h(TodoDemo, {}),
        h(MountDemo, {}),
        h(PortalDemo, {}),
        class_name="page",
    )
