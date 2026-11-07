"""Router feature: params, query strings, wildcards, nested paths, and not-found.

The ``Index`` page links to sub-routes resolved by the app-level router
(see :func:`app.routes.create_routes`). Each sub-page renders a marker plus
the value the router extracted from the URL. The links are plain anchors,
which the router follows without reloading the page.
Routed pages that read the URL take ``RouteProps``, whose ``params`` and
``query`` read as values; the rest take nothing.
"""

from wybthon import component, html
from wybthon.router import Outlet, RouteProps


@component
def Index():
    return html(t"""
      <div data-testid="page-router">
        <h2>Router</h2>
        <a href="/router/user/42" data-testid="router-link-user">user 42</a>
        <a href="/router/search?q=hello" data-testid="router-link-search">search hello</a>
        <a href="/router/docs/guide/intro" data-testid="router-link-docs">docs</a>
        <a href="/router/parent" data-testid="router-link-parent">parent</a>
        <a href="/router/parent/child" data-testid="router-link-child">child</a>
        <a href="/router/nope" data-testid="router-link-missing">missing</a>
      </div>
    """)


@component
def User(props: RouteProps):
    return html(t"""
      <div data-testid="page-router-user">
        <span data-testid="router-user-marker">user</span>
        <span data-testid="router-user-id">{props.params.get("id", "")}</span>
      </div>
    """)


@component
def Search(props: RouteProps):
    return html(t"""
      <div data-testid="page-router-search"><span data-testid="router-search-q">{props.search.get("q", "")}</span></div>
    """)


@component
def Docs(props: RouteProps):
    return html(t"""
      <div data-testid="page-router-docs">
        <span data-testid="router-docs-rest">{props.params.get("wildcard", "")}</span>
      </div>
    """)


@component
def Parent():
    return html(t"""
      <div data-testid="page-router-parent"><span data-testid="router-parent-marker">parent</span>{Outlet()}</div>
    """)


@component
def Child():
    return html(t'<div data-testid="page-router-child"><span data-testid="router-child-marker">child</span></div>')
