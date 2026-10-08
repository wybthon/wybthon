"""Context API: provider value propagation, nested override, and default fallback."""

from app.testkit import tid

from wybthon import Props, button, component, create_context, create_signal, div, h2, p, span, use_context

Theme = create_context("default-theme")


class ThemeLabelProps(Props):
    test_id: str


@component
def ThemeLabel(props: ThemeLabelProps):
    # The provided value is handed back as is: an accessor stays live, a
    # plain string renders once.
    theme = use_context(Theme)
    return span(theme, **tid(props.test_id))


@component
def Page():
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
            on_click=lambda: set_theme(lambda t: "dark" if t == "light" else "light"),
            **tid("ctx-toggle"),
        ),
        **tid("page-context"),
    )
