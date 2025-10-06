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
    # TODO: Refactor base_path detection to use a stable source.
    # Prefer deriving from a <base href> or a bootstrap-provided
    # window.WYBTHON_BASE_PATH (fall back to "/"), and consider rendering Nav
    # under Router so Link can read base from context without prop threading.
    # Detect the base path from the current page's location so routing works when
    # the demo is served from a subdirectory like "/examples/demo".
    path = str(window.location.pathname) or "/"
    if path.endswith(".html"):
        # If loaded via .../index.html, strip the filename to get the directory
        path = path.rsplit("/", 1)[0] or "/"
    # Use directory path without trailing slash (except for root)
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
