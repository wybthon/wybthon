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

from wybthon import Link, Prop, component, div, nav, prop


def _join(base_path: str, to: str) -> str:
    if not base_path or base_path == "/":
        return to
    return base_path.rstrip("/") + to


def _nav_link(base_path: str, to: str, label: str, slug: str):
    return Link(
        label,
        href=_join(base_path, to),
        class_="nav-link",
        active_class="active",
        end=True,
        **tid(f"nav-{slug}"),
    )


@component
def Shell(children: Prop = prop(None), base_path: Prop[str] = prop("")):
    bp = base_path.peek() or ""
    links = [_nav_link(bp, "/", "Home", "home")]
    links += [_nav_link(bp, f"/{slug}", label, slug) for slug, label in FEATURES]
    links.append(_nav_link(bp, "/blank", "Blank", "blank"))

    return div(
        nav(*links, **tid("nav")),
        div(children, **tid("outlet")),
        div("ready", **tid("app-ready")),
        **tid("shell"),
    )
