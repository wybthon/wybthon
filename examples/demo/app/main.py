from js import window

from app.components.counter import Counter
from app.components.hello import Hello
from app.components.theme_label import ThemeLabel
from app.layout import Layout
from app.not_found import NotFound
from app.routes import create_routes
from wybthon import Element, Router, h, render


async def main():
    routes = create_routes()
    path = str(window.location.pathname) or "/"
    if path.endswith(".html"):
        path = path.rsplit("/", 1)[0] or "/"
    base_path = "/" if path == "/" else path.rstrip("/")

    tree = h(
        Layout,
        {"base_path": base_path},
        h(Router, {"routes": routes, "not_found": NotFound, "base_path": base_path}),
        h(ThemeLabel, {}),
        h(Counter, {}),
        h(Hello, {"name": "Python"}),
    )

    container = Element("body", existing=True)
    render(tree, container)
