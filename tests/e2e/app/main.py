"""Entry point for the Wybthon end-to-end fixture project.

The fixture is an ordinary Wybthon project (`tests/e2e/wybthon.toml`) that
`wyb dev` builds and serves. The production bootstrap calls `app()` for the
root view and renders it into `#app`; it records its status on
`window.__WYB`, which the Playwright harness waits on.

`app()` also exposes `window.__wyb_e2e_goto` for programmatic navigation.
The shell renders a `data-testid="app-ready"` marker, the visible readiness
signal.
"""

from app.routes import create_routes
from app.shell import Shell
from js import window
from pyodide.ffi import create_proxy

from wybthon.router import create_router, navigate

router = create_router(create_routes())


def app():
    window.__wyb_e2e_goto = create_proxy(lambda path: navigate(str(path)))
    return router(root=Shell)
