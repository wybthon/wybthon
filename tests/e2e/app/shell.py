"""Navigation shell that wraps the feature router.

The shell is mounted once for the lifetime of the page (the router swaps
feature pages beneath it on client-side navigation), so its
``data-testid="app-ready"`` marker is a stable readiness signal: once it is
present, Pyodide booted and the first route rendered.

The nav sits outside the ``Router``, so it joins the served base path into
each ``href`` itself; links rendered inside routed pages get that for free
from the router's context.
"""

from app.featuremeta import FEATURES
from app.testkit import tid

from wybthon import ParentProps, component, html
from wybthon.router import Link


def _join(base_path: str, to: str) -> str:
    if not base_path or base_path == "/":
        return to
    return base_path.rstrip("/") + to


class ShellProps(ParentProps):
    base_path: str = ""


@component
def Shell(props: ShellProps):
    # A constant prop: reading it once in the body is fine.
    bp = props.base_path or ""
    pages = [
        ("/", "Home", "home"),
        *((f"/{slug}", label, slug) for slug, label in FEATURES),
        ("/blank", "Blank", "blank"),
    ]
    # The comprehension variables are captured by value in each link's getters.
    links = [
        html(t"""
          <{Link} href={_join(bp, to)} class="nav-link" active-class="active" end={True} {tid(f"nav-{slug}")}>
            {label}
          </{Link}>
        """)
        for to, label, slug in pages
    ]

    return html(t"""
      <div data-testid="shell">
        <nav data-testid="nav">{links}</nav>
        <div data-testid="outlet">{props.children}</div>
        <div data-testid="app-ready">ready</div>
      </div>
    """)
