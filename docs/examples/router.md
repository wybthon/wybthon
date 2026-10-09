# Router

Client-side routing with [`Router`][wybthon.router.Router], [`Route`][wybthon.router.Route], and [`Link`][wybthon.router.Link] from `wybthon.router`, including path parameters, query strings, nested routes, and lazy-loaded pages.

```python
from wybthon import Errored, Loading, component, html, lazy, render
from wybthon.router import Link, Outlet, Route, RouteProps, Router, current_path


@component
def Home():
    return html(t"<div><h1>Home</h1><p>Welcome.</p></div>")


@component
def About():
    # Child routes (here, /about/team) render at the Outlet.
    return html(t"<div><h1>About</h1><p>A small routed app.</p>{Outlet()}</div>")


@component
def User(props: RouteProps):
    # ``props.params`` and ``props.query`` are accessors. Navigating from
    # /users/1 to /users/2 updates them in place; the component isn't remounted.
    def user_id():
        return props.params()["user_id"]

    def tab():
        return props.query().get("tab", "info")

    return html(t"<div><h1>User {user_id}</h1><p>Tab: {tab}</p></div>")


@component
def NotFound():
    return html(t"<div><h1>Not found</h1><p>No page at {current_path}</p></div>")


# Loaded on first visit; the import runs inside an async memo.
Team = lazy(lambda: ("app.about.team", "Page"))

routes = [
    Route("/", Home),
    Route("/about", About, children=[Route("team", Team)]),
    Route("/users/:user_id", User),
]


def page_failed(err, reset):
    return html(t"<p>Page failed to load: {(lambda: str(err()))}</p>")


@component
def App():
    return html(t"""
      <div>
        <nav>
          <ul>
            <li>{Link("Home", href="/", end=True)}</li>
            <li>{Link("About", href="/about")}</li>
            <li>{Link("Team", href="/about/team", on_mouseenter=Team.preload)}</li>
            <li>{Link("User 1", href="/users/1?tab=posts")}</li>
          </ul>
        </nav>
        <main>
          {
        Errored(
            Loading(Router(routes, not_found=NotFound), fallback=html(t"<p>Loading page...</p>")),
            fallback=page_failed,
            reset_on=current_path,
        )
    }
        </main>
      </div>
    """)


render(App(), "#app")
```

## How it works

- [`Router`][wybthon.router.Router] reads [`current_path`][wybthon.router.current_path] and renders the component of the first matching [`Route`][wybthon.router.Route]. Only a change in *which* route matches re-mounts the outlet; param and query changes flow into the mounted component as prop updates.
- The matched component receives `params` and `query` as props. Declare them by annotating the component's parameter with [`RouteProps`][wybthon.router.RouteProps], or subclass it to add fields of your own. Both are dicts, so `User` reads them inside the `user_id` and `tab` functions, which the template turns into holes. Outside the route component, [`use_params`][wybthon.router.use_params] and [`use_query`][wybthon.router.use_query] return the same accessors.
- [`Link`][wybthon.router.Link] renders an `<a>` that navigates with the History API. It adds `active_class` (default `"active"`) while its path matches; `end=True` requires an exact match, which keeps "Home" from being active everywhere. Modifier-key clicks and middle clicks pass through to the browser. `Link` works as a call in an interpolation or as a `<{Link} href="/">...</{Link}>` tag.
- Nested `Route.children` paths are joined with the parent path, so `Route("team", Team)` under `/about` matches `/about/team`. The parent renders the matched child wherever it places [`Outlet()`][wybthon.router.Outlet].
- Wrapping the router in [`Loading`][wybthon.Loading] and [`Errored`][wybthon.Errored] with `reset_on=current_path` gives every page a loading state and an error state that clears on navigation. The error fallback reads the error through the `err` accessor. An interpolation can span several lines, as the `Errored(...)` call does here.

## Programmatic navigation

```python
from wybthon.router import navigate

navigate("/about")
navigate("/users/2?tab=info", replace=True)
```

Outside a browser (for example in unit tests), `navigate` only updates the `current_path` signal; call [`flush`][wybthon.flush] afterward to apply it.

## Lazy routes

[`lazy`][wybthon.lazy] takes a loader that returns a component, a module, a module path string, or a `(module_path, attr)` tuple. The loader may be `async def`, so it can `await micropip.install(...)` first. Call `.preload()` on user intent (hover, focus) to warm the import before the click:

```python
from wybthon import lazy


async def load_docs():
    import micropip

    await micropip.install("my-docs-package")
    from my_docs import DocsPage

    return DocsPage


Docs = lazy(load_docs)
```

## Base paths

Serve the app under a prefix by passing `base_path`; `Link` prepends it and the router strips it before matching:

```python
from wybthon.router import Router

Router(routes, base_path="/app")
```

Inside the tree, [`use_base_path`][wybthon.router.use_base_path] returns the active base path.

## Wildcards

A trailing `/*` matches any remainder:

```python
from wybthon.router import Route

Route("/docs/*", Docs)
```

## Next steps

- Read the [Router](../concepts/router.md) concept page.
- See [Async and Loading](../concepts/async-loading.md) for code-splitting routes.
- Browse the [`router`][wybthon.router] API, including [`resolve`][wybthon.router.resolve] for matching paths without a browser.
