"""Mini SPA — multi-page client-side app in 35 lines of Python.

Tweet caption:
    A multi-page Single Page App, in Python. Client-side routing, links,
    path params, and a 404 — all in one screenshot.

Why it's interesting:
    `Router` matches the URL and mounts the right component. `Link`
    handles navigation without a page reload. Path params arrive in
    `props["params"]`. No JavaScript glue required.
"""

from wybthon import Link, Route, Router, component, div, h, h1, h2, nav, p


@component
def Home(props):
    return div(h1("Home"), p("Welcome to a Python SPA."))


@component
def About(props):
    return div(h1("About"), p("Built with Wybthon, running in Pyodide."))


@component
def User(props):
    user_id = props["params"]["user_id"]
    return div(h1("User profile"), p(f"User #{user_id}"))


@component
def NotFound(props):
    return div(h2("404"), p("This page is not here."))


routes = [
    Route(path="/", component=Home),
    Route(path="/about", component=About),
    Route(path="/users/:user_id", component=User),
]


@component
def App():
    return div(
        nav(
            h(Link, {"to": "/", "children": ["Home"]}),
            " · ",
            h(Link, {"to": "/about", "children": ["About"]}),
            " · ",
            h(Link, {"to": "/users/42", "children": ["User #42"]}),
        ),
        h(Router, {"routes": routes, "not_found": NotFound}),
    )
