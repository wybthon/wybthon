"""Router feature: params, query strings, wildcards, nested paths, and not-found.

The ``Index`` page links to sub-routes resolved by the app-level ``Router``
(see :func:`app.routes.create_routes`). Each sub-page renders a marker plus
the value the router extracted from the URL.
"""

from app.testkit import tid

from wybthon import Link, component, div, dynamic, h, h2, span


def _link(to, label, slug):
    return h(Link, {"to": to, "data-testid": f"router-link-{slug}"}, label)


@component
def Index(query=None, params=None):
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
def User(params=None, query=None):
    return div(
        span("user", **tid("router-user-marker")),
        span(dynamic(lambda: (params() or {}).get("id", "")), **tid("router-user-id")),
        **tid("page-router-user"),
    )


@component
def Search(query=None, params=None):
    return div(
        span(dynamic(lambda: (query() or {}).get("q", "")), **tid("router-search-q")),
        **tid("page-router-search"),
    )


@component
def Docs(params=None, query=None):
    return div(
        span(dynamic(lambda: (params() or {}).get("wildcard", "")), **tid("router-docs-rest")),
        **tid("page-router-docs"),
    )


@component
def Parent(params=None, query=None):
    return div(span("parent", **tid("router-parent-marker")), **tid("page-router-parent"))


@component
def Child(params=None, query=None):
    return div(span("child", **tid("router-child-marker")), **tid("page-router-child"))
