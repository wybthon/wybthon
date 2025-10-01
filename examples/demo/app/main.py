from wybthon import h, render, Element, Router
from app.routes import create_routes
from app.layout import Layout
from app.components.counter import Counter
from app.components.hello import Hello
from app.components.theme_label import ThemeLabel


async def main():
    routes = create_routes()

    tree = h(
        Layout,
        {},
        h(Router, {"routes": routes}),
        h(ThemeLabel, {}),
        h(Counter, {}),
        h(Hello, {"name": "Python"}),
    )

    container = Element("body", existing=True)
    render(tree, container)
