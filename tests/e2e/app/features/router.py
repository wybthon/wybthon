"""Router feature: params, query strings, wildcards, nested paths, and not-found.

The ``Index`` page links to sub-routes resolved by the app-level ``Router``
(see :func:`app.routes.create_routes`). Each sub-page renders a marker plus
the value the router extracted from the URL. ``Link`` joins ``href`` with
the router's base path automatically because these pages render inside it.
Routed pages that read the URL take ``RouteProps``; the rest take nothing.
"""

from app.testkit import tid

from wybthon import component, div, h2, span
from wybthon.router import Link, Outlet, RouteProps


def _link(to, label, slug):
    return Link(label, href=to, **tid(f"router-link-{slug}"))


@component
def Index():
    return div(
        h2("Router"),
        _link("/router/user/42", "user 42", "user"),
        _link("/router/search?q=hello", "search hello", "search"),
        _link("/router/docs/guide/intro", "docs", "docs"),
        _link("/router/parent", "parent", "parent"),
        _link("/router/parent/child", "child", "child"),
        _link("/router/nope", "missing", "missing"),
        **tid("page-router"),
    )


@component
def User(props: RouteProps):
    return div(
        span("user", **tid("router-user-marker")),
        span(lambda: props.params().get("id", ""), **tid("router-user-id")),
        **tid("page-router-user"),
    )


@component
def Search(props: RouteProps):
    return div(
        span(lambda: props.query().get("q", ""), **tid("router-search-q")),
        **tid("page-router-search"),
    )


@component
def Docs(props: RouteProps):
    return div(
        span(lambda: props.params().get("wildcard", ""), **tid("router-docs-rest")),
        **tid("page-router-docs"),
    )


@component
def Parent():
    return div(span("parent", **tid("router-parent-marker")), Outlet(), **tid("page-router-parent"))


@component
def Child():
    return div(span("child", **tid("router-child-marker")), **tid("page-router-child"))
