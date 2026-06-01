"""Context API: provider value propagation, nested override, and default fallback."""

from app.testkit import tid

from wybthon import (
    Provider,
    button,
    component,
    create_context,
    create_signal,
    div,
    dynamic,
    h,
    h2,
    p,
    span,
    use_context,
)

Theme = create_context("default-theme")


@component
def Page():
    theme, set_theme = create_signal("light")

    return div(
        h2("Context"),
        h(
            Provider,
            {"context": Theme, "value": theme},
            div(
                p("outer: ", span(dynamic(lambda: use_context(Theme)), **tid("ctx-outer"))),
                h(
                    Provider,
                    {"context": Theme, "value": "override"},
                    p("inner: ", span(dynamic(lambda: use_context(Theme)), **tid("ctx-inner"))),
                ),
            ),
        ),
        p("no provider: ", span(dynamic(lambda: use_context(Theme)), **tid("ctx-default"))),
        button("toggle", on_click=lambda e: set_theme("dark" if theme() == "light" else "light"), **tid("ctx-toggle")),
        **tid("page-context"),
    )
