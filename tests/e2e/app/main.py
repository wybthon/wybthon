"""Entrypoint for the Wybthon E2E fixture single-page app.

Boot sequence:

1. Compute the served base path (so the fixture works whether it is served
   from ``/`` or ``/tests/e2e/index.html``).
2. Mount the navigation shell wrapping the feature ``Router``.
3. Remove the loading placeholder.
4. Expose ``window.__wyb_e2e_goto`` for programmatic navigation and flip
   ``window.__WYB_E2E_READY`` so the Playwright harness can detect readiness
   without racing the Pyodide boot.

The shell also renders a ``data-testid="app-ready"`` marker, which is the
primary readiness signal the harness waits on.
"""

from app.routes import NotFound, create_routes
from app.shell import Shell
from js import document, window
from pyodide.ffi import create_proxy

from wybthon import Element, Router, current_path, h, navigate, render


def _compute_base_path() -> str:
    path = str(window.location.pathname) or "/"
    if path.endswith(".html"):
        path = path.rsplit("/", 1)[0] or "/"
    return "/" if path == "/" else path.rstrip("/")


async def main() -> None:
    base_path = _compute_base_path()
    current_path.set(base_path or "/")

    routes = create_routes()
    tree = h(
        Shell,
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

    def _goto(path: str) -> None:
        target = str(path)
        if base_path and base_path != "/" and target.startswith("/"):
            navigate(base_path.rstrip("/") + target)
        else:
            navigate(target)

    window.__wyb_e2e_goto = create_proxy(_goto)
    window.__WYB_E2E_READY = True
