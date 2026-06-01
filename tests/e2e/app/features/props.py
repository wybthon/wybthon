"""Reactive props: class, style, dataset attributes, and controlled inputs."""

from app.testkit import tid

from wybthon import button, component, create_signal, div, dynamic, h2, input_, span

_COLORS = {"teal": "red", "red": "blue", "blue": "teal"}
_STATES = {"idle": "busy", "busy": "done", "done": "idle"}


@component
def Page():
    danger, set_danger = create_signal(False)
    color, set_color = create_signal("teal")
    state, set_state = create_signal("idle")
    text, set_text = create_signal("")
    checked, set_checked = create_signal(False)

    return div(
        h2("Props"),
        div(
            span("status", class_=lambda: "pill danger" if danger() else "pill", **tid("props-class")),
            button("toggle danger", on_click=lambda e: set_danger(not danger()), **tid("props-class-btn")),
        ),
        div(
            span("colored", style=lambda: {"color": color()}, **tid("props-style")),
            button("cycle color", on_click=lambda e: set_color(_COLORS[color()]), **tid("props-style-btn")),
        ),
        div(
            span("attr", dataset=lambda: {"state": state()}, **tid("props-attr")),
            button("cycle state", on_click=lambda e: set_state(_STATES[state()]), **tid("props-attr-btn")),
        ),
        div(
            input_(value=text, on_input=lambda e: set_text(e.target.value), **tid("props-input")),
            span(text, **tid("props-input-echo")),
            button("set hello", on_click=lambda e: set_text("hello"), **tid("props-input-set")),
        ),
        div(
            input_(
                type="checkbox",
                checked=checked,
                on_change=lambda e: set_checked(e.target.checked),
                **tid("props-check"),
            ),
            span(dynamic(lambda: "on" if checked() else "off"), **tid("props-check-echo")),
        ),
        **tid("page-props"),
    )
