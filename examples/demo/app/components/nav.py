from wybthon import Link, component, h, nav


@component
def Nav(base_path=None):
    lp = {"base_path": base_path, "class": "nav-link", "class_active": "active"}
    return nav(
        h(Link, {**lp, "to": "/"}, "Home"),
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
        class_name="app-nav",
    )
