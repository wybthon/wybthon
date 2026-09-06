"""Context API: provider value propagation, nested override, and default fallback."""

from app.testkit import tid

from wybthon import Prop, button, component, create_context, create_signal, div, h2, p, span, use_context

Theme = create_context("default-theme")


@component
def ThemeLabel(test_id: Prop[str]):
    # The provided value is handed back as is: an accessor stays live, a
    # plain string renders once.
    theme = use_context(Theme)
    return span(theme, **tid(test_id.peek()))


@component
def Page(**rest):
    theme, set_theme = create_signal("light")

    return div(
        h2("Context"),
        Theme(
            theme,
            div(
                p("outer: ", ThemeLabel(test_id="ctx-outer")),
                Theme("override", p("inner: ", ThemeLabel(test_id="ctx-inner"))),
            ),
        ),
        p("no provider: ", ThemeLabel(test_id="ctx-default")),
        button(
            "toggle",
            on_click=lambda e: set_theme(lambda t: "dark" if t == "light" else "light"),
            **tid("ctx-toggle"),
        ),
        **tid("page-context"),
    )
