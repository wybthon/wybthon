"""Navigation shell: the router's root layout.

The shell is mounted once for the lifetime of the page (the router swaps
feature pages beneath it on client-side navigation), so its
``data-testid="app-ready"`` marker is a stable readiness signal: once it is
present, Pyodide booted and the first route rendered.

Each nav link is a plain anchor whose class follows `use_link_state`.
"""

from app.featuremeta import FEATURES
from app.testkit import tid

from wybthon import Children, component, html
from wybthon.router import use_link_state


@component
def NavLink(href: str, slug: str, children: Children = None):
    state = use_link_state(lambda: href, end=True)
    return html(t"""
      <a href={href} class={"nav-link active" if state.active() else "nav-link"} {tid(f"nav-{slug}")}>
        {children}
      </a>
    """)


@component
def Shell(children: Children = None):
    pages = [
        ("/", "Home", "home"),
        *((f"/{slug}", label, slug) for slug, label in FEATURES),
        ("/blank", "Blank", "blank"),
    ]
    links = [NavLink(href=to, slug=slug, children=label) for to, label, slug in pages]

    return html(t"""
      <div data-testid="shell">
        <nav data-testid="nav">{links}</nav>
        <div data-testid="outlet">{children}</div>
        <div data-testid="app-ready">ready</div>
      </div>
    """)
