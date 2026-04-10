from app.components.nav import Nav
from app.contexts.theme import Theme
from wybthon import Provider, component, div, footer, h, h1, header, main_, p, span


@component
def Layout(base_path="", children=None):
    _ch = children
    kids = _ch if isinstance(_ch, list) else ([_ch] if _ch else [])
    return div(
        header(
            div(
                span("W", class_name="logo-icon"),
                h1("Wybthon"),
                class_name="header-brand",
            ),
            h(Nav, {"base_path": base_path}),
            class_name="app-header",
        ),
        h(
            Provider,
            {"context": Theme, "value": "dark"},
            main_(*kids, class_name="app-main"),
        ),
        footer(
            p("Built with Wybthon + Pyodide"),
            class_name="app-footer",
        ),
        id="app",
    )
