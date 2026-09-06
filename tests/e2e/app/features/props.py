"""Reactive props: class, style, dataset attributes, and controlled inputs."""

from app.testkit import tid

from wybthon import button, component, create_signal, div, h2, input_, span

_COLORS = {"teal": "red", "red": "blue", "blue": "teal"}
_STATES = {"idle": "busy", "busy": "done", "done": "idle"}


@component
def Page(**rest):
    danger, set_danger = create_signal(False)
    color, set_color = create_signal("teal")
    state, set_state = create_signal("idle")
    text, set_text = create_signal("")
    checked, set_checked = create_signal(False)

    return div(
        h2("Props"),
        div(
            span("status", class_={"pill": True, "danger": danger}, **tid("props-class")),
            button("toggle danger", on_click=lambda e: set_danger(lambda d: not d), **tid("props-class-btn")),
        ),
        div(
            span("colored", style={"color": color}, **tid("props-style")),
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
            span(lambda: "on" if checked() else "off", **tid("props-check-echo")),
        ),
        **tid("page-props"),
    )
