"""Reactive "holes": text holes, derived expressions, node holes, and independence."""

from app.testkit import tid

from wybthon import button, component, create_signal, div, dynamic, em, h2, input_, p, span, strong, untrack


@component
def Page():
    count, set_count = create_signal(0)

    first, set_first = create_signal("Ada")
    last, set_last = create_signal("Lovelace")

    mode, set_mode = create_signal("a")

    def node_hole():
        m = mode()
        if m == "a":
            return span("alpha", **tid("hole-node-inner"))
        if m == "b":
            return strong("bravo", **tid("hole-node-inner"))
        return em("charlie", **tid("hole-node-inner"))

    def next_mode(_e):
        set_mode({"a": "b", "b": "c", "c": "a"}[mode()])

    x, set_x = create_signal(0)
    y, set_y = create_signal(0)
    x_runs, set_x_runs = create_signal(0)
    y_runs, set_y_runs = create_signal(0)

    def x_view():
        set_x_runs(untrack(x_runs) + 1)
        return str(x())

    def y_view():
        set_y_runs(untrack(y_runs) + 1)
        return str(y())

    return div(
        h2("Holes"),
        div(
            p("text: ", span(count, **tid("hole-text"))),
            button("+1", on_click=lambda e: set_count(count() + 1), **tid("hole-text-inc")),
        ),
        div(
            input_(value=first, on_input=lambda e: set_first(e.target.value), **tid("hole-first")),
            input_(value=last, on_input=lambda e: set_last(e.target.value), **tid("hole-last")),
            span(dynamic(lambda: f"Hello, {first()} {last()}!"), **tid("hole-greeting")),
        ),
        div(
            p("node: ", span(node_hole, **tid("hole-node"))),
            button("cycle", on_click=next_mode, **tid("hole-node-cycle")),
        ),
        div(
            p("x: ", span(x_view, **tid("hole-x")), " runs: ", span(x_runs, **tid("hole-x-runs"))),
            p("y: ", span(y_view, **tid("hole-y")), " runs: ", span(y_runs, **tid("hole-y-runs"))),
            button("inc x", on_click=lambda e: set_x(x() + 1), **tid("hole-x-inc")),
            button("inc y", on_click=lambda e: set_y(y() + 1), **tid("hole-y-inc")),
        ),
        **tid("page-holes"),
    )
