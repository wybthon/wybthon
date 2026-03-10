from app.components.nav import Nav
from app.contexts.theme import Theme
from wybthon import Provider, component, div, h, h1


@component
def Layout(base_path="", children=None):
    kids = children if isinstance(children, list) else ([children] if children else [])
    return div(
        h1("Wybthon VDOM Demo"),
        h(Nav, {"base_path": base_path}),
        h(Provider, {"context": Theme, "value": "dark"}, kids),
        id="app",
    )
