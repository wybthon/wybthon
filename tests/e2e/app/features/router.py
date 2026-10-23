"""Router feature: params, query strings, wildcards, nested paths, and not-found.

The ``Index`` page links to sub-routes resolved by the app-level ``Router``
(see :func:`app.routes.create_routes`). Each sub-page renders a marker plus
the value the router extracted from the URL. ``Link`` joins ``href`` with
the router's base path automatically because these pages render inside it.
Routed pages that read the URL take ``RouteProps``, whose ``params`` and
``query`` read as values; the rest take nothing.
"""

from wybthon import component, html
from wybthon.router import Link, Outlet, RouteProps


@component
def Index():
    return html(t"""
      <div data-testid="page-router">
        <h2>Router</h2>
        <{Link} href="/router/user/42" data-testid="router-link-user">user 42</{Link}>
        <{Link} href="/router/search?q=hello" data-testid="router-link-search">search hello</{Link}>
        <{Link} href="/router/docs/guide/intro" data-testid="router-link-docs">docs</{Link}>
        <{Link} href="/router/parent" data-testid="router-link-parent">parent</{Link}>
        <{Link} href="/router/parent/child" data-testid="router-link-child">child</{Link}>
        <{Link} href="/router/nope" data-testid="router-link-missing">missing</{Link}>
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
      <div data-testid="page-router-search"><span data-testid="router-search-q">{props.query.get("q", "")}</span></div>
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
