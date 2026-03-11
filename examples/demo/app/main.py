from js import document, window

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
    )

    container = Element("body", existing=True)
    render(tree, container)

    try:
        loading = document.getElementById("loading")
        if loading:
            loading.remove()
    except Exception:
        pass
