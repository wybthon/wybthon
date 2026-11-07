"""Navigation shell: the router's root layout.

The shell is mounted once for the lifetime of the page (the router swaps
feature pages beneath it on client-side navigation), so its
``data-testid="app-ready"`` marker is a stable readiness signal: once it is
present, Pyodide booted and the first route rendered.

Each nav link is a plain anchor whose class follows `use_link_state`.
"""

from app.featuremeta import FEATURES
from app.testkit import tid

from wybthon import ParentProps, component, html
from wybthon.router import use_link_state


class NavLinkProps(ParentProps):
    href: str
    slug: str


@component
def NavLink(props: NavLinkProps):
    state = use_link_state(lambda: props.href, end=True)
    return html(t"""
      <a href={props.href} class={"nav-link active" if state.active() else "nav-link"} {tid(f"nav-{props.slug}")}>
        {props.children}
      </a>
    """)


@component
def Shell(props: ParentProps):
    pages = [
        ("/", "Home", "home"),
        *((f"/{slug}", label, slug) for slug, label in FEATURES),
        ("/blank", "Blank", "blank"),
    ]
    links = [NavLink(href=to, slug=slug, children=label) for to, label, slug in pages]

    return html(t"""
      <div data-testid="shell">
        <nav data-testid="nav">{links}</nav>
        <div data-testid="outlet">{props.children}</div>
        <div data-testid="app-ready">ready</div>
      </div>
    """)
