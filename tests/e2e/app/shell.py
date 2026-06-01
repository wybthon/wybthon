"""Navigation shell that wraps the feature router.

The shell is mounted once for the lifetime of the page (the router swaps
feature pages beneath it on client-side navigation), so its
``data-testid="app-ready"`` marker is a stable readiness signal: once it is
present, Pyodide booted and the first route rendered.
"""

from app.featuremeta import FEATURES
from app.testkit import tid

from wybthon import Link, component, div, h, nav, untrack


def _nav_link(base_path: str, to: str, label: str, slug: str):
    return h(
        Link,
        {
            "to": to,
            "base_path": base_path,
            "class": "nav-link",
            "class_active": "active",
            "data-testid": f"nav-{slug}",
        },
        label,
    )


@component
def Shell(base_path="", children=None):
    bp = untrack(base_path) if callable(base_path) else base_path
    kids = untrack(children) if callable(children) else children
    if kids is None:
        kids = []
    if not isinstance(kids, list):
        kids = [kids]

    links = [_nav_link(bp, "/", "Home", "home")]
    links += [_nav_link(bp, f"/{slug}", label, slug) for slug, label in FEATURES]
    links.append(_nav_link(bp, "/blank", "Blank", "blank"))

    return div(
        nav(*links, **tid("nav")),
        div(*kids, **tid("outlet")),
        div("ready", **tid("app-ready")),
        **tid("shell"),
    )
