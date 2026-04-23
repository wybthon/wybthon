from wybthon import Link, component, h, nav, untrack


@component
def Nav(base_path=None):
    bp = untrack(base_path)
    lp = {"base_path": bp, "class": "nav-link", "class_active": "active"}
    return nav(
        h(Link, {**lp, "to": "/"}, "Home"),
        h(Link, {**lp, "to": "/props"}, "Props"),
        h(Link, {**lp, "to": "/holes"}, "Holes"),
        h(Link, {**lp, "to": "/primitives"}, "Primitives"),
        h(Link, {**lp, "to": "/patterns"}, "Patterns"),
        h(Link, {**lp, "to": "/stores"}, "Stores"),
        h(Link, {**lp, "to": "/flow"}, "Flow"),
        h(Link, {**lp, "to": "/forms"}, "Forms"),
        h(Link, {**lp, "to": "/fetch"}, "Fetch"),
        h(Link, {**lp, "to": "/errors"}, "Errors"),
        h(Link, {**lp, "to": "/about"}, "About"),
        h(Link, {**lp, "to": "/docs"}, "Docs"),
        class_="app-nav",
    )
