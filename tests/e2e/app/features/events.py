"""Event delegation: bubbling, stopPropagation, and target value/checked reads."""

from app.testkit import tid

from wybthon import button, component, create_signal, div, dynamic, h2, input_, p, span


@component
def Page():
    outer, set_outer = create_signal(0)
    inner, set_inner = create_signal(0)
    text, set_text = create_signal("")
    checked, set_checked = create_signal(False)

    def on_outer(_e):
        set_outer(outer() + 1)

    def on_inner_stop(e):
        e.stop_propagation()
        set_inner(inner() + 1)

    def on_inner_bubble(_e):
        set_inner(inner() + 1)

    return div(
        h2("Events"),
        div(
            p("outer clicks: ", span(outer, **tid("ev-outer-count"))),
            p("inner clicks: ", span(inner, **tid("ev-inner-count"))),
            button("inner (stop)", on_click=on_inner_stop, **tid("ev-inner-stop")),
            button("inner (bubble)", on_click=on_inner_bubble, **tid("ev-inner-bubble")),
            on_click=on_outer,
            **tid("ev-outer"),
        ),
        div(
            input_(on_input=lambda e: set_text(e.target.value), **tid("ev-input")),
            span(text, **tid("ev-input-echo")),
            input_(type="checkbox", on_change=lambda e: set_checked(e.target.checked), **tid("ev-check")),
            span(dynamic(lambda: "on" if checked() else "off"), **tid("ev-check-echo")),
        ),
        **tid("page-events"),
    )
