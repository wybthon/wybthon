from app.components.nav import Nav
from app.contexts.theme import Theme
from wybthon import (
    Provider,
    button,
    component,
    create_signal,
    div,
    dynamic,
    footer,
    h,
    h1,
    header,
    main_,
    p,
    span,
    untrack,
)


@component
def Layout(base_path="", children=None):
    """App shell with reactive theme toggle.

    Demonstrates the new fully-reactive context: switching the
    ``theme`` signal flows through the Provider into every consumer
    without any subtree being re-mounted.
    """
    bp = untrack(base_path)
    kids = untrack(children) if callable(children) else children
    if kids is None:
        kids = []
    if not isinstance(kids, list):
        kids = [kids]

    theme, set_theme = create_signal("dark")

    def toggle(_evt):
        set_theme("light" if theme() == "dark" else "dark")

    return div(
        header(
            div(
                span("W", class_="logo-icon"),
                h1("Wybthon"),
                button(
                    dynamic(lambda: f"Theme: {theme()}"),
                    on_click=toggle,
                    class_="theme-toggle",
                ),
                class_="header-brand",
            ),
            h(Nav, {"base_path": bp}),
            class_="app-header",
        ),
        h(
            Provider,
            {"context": Theme, "value": theme},
            main_(*kids, class_="app-main"),
        ),
        footer(
            p("Built with Wybthon + Pyodide"),
            class_="app-footer",
        ),
        id="app",
    )
