from app.components.nav import Nav
from app.contexts.theme import Theme
from wybthon import Provider, h


def Layout(props):
    children = props.get("children", [])
    if not isinstance(children, list):
        children = [children]
    return h(
        "div",
        {"id": "app"},
        h("h1", {}, "Wybthon VDOM Demo"),
        h(Nav, {}),
        h(Provider, {"context": Theme, "value": "dark"}, children),
    )
