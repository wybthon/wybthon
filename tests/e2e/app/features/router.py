"""Router feature: params, query strings, wildcards, nested paths, and not-found.

The ``Index`` page links to sub-routes resolved by the app-level ``Router``
(see :func:`app.routes.create_routes`). Each sub-page renders a marker plus
the value the router extracted from the URL. ``Link`` joins ``href`` with
the router's base path automatically because these pages render inside it.
"""

from app.testkit import tid

from wybthon import Link, Prop, component, div, h2, span


def _link(to, label, slug):
    return Link(label, href=to, **tid(f"router-link-{slug}"))


@component
def Index(**rest):
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
def User(params: Prop[dict], **rest):
    return div(
        span("user", **tid("router-user-marker")),
        span(lambda: (params() or {}).get("id", ""), **tid("router-user-id")),
        **tid("page-router-user"),
    )


@component
def Search(query: Prop[dict], **rest):
    return div(
        span(lambda: (query() or {}).get("q", ""), **tid("router-search-q")),
        **tid("page-router-search"),
    )


@component
def Docs(params: Prop[dict], **rest):
    return div(
        span(lambda: (params() or {}).get("wildcard", ""), **tid("router-docs-rest")),
        **tid("page-router-docs"),
    )


@component
def Parent(**rest):
    return div(span("parent", **tid("router-parent-marker")), **tid("page-router-parent"))


@component
def Child(**rest):
    return div(span("child", **tid("router-child-marker")), **tid("page-router-child"))
