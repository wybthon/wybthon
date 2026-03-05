from app.components.nav import Nav
from app.contexts.theme import Theme
from wybthon import Provider, div, h, h1


def Layout(props):
    base_path = props.get("base_path", "")
    children = props.get("children", [])
    if not isinstance(children, list):
        children = [children]
    return div(
        h1("Wybthon VDOM Demo"),
        h(Nav, {"base_path": base_path}),
        h(Provider, {"context": Theme, "value": "dark"}, children),
        id="app",
    )
