# Router

Client-side routing with [`Router`][wybthon.Router], [`Route`][wybthon.Route], and [`Link`][wybthon.Link], including path parameters, query strings, nested routes, and lazy-loaded pages.

```python
from wybthon import (
    Errored,
    Link,
    Loading,
    Prop,
    Route,
    Router,
    component,
    current_path,
    div,
    h1,
    lazy,
    li,
    main_,
    nav,
    navigate,
    p,
    render,
    ul,
    use_query,
)


@component
def Home():
    return div(h1("Home"), p("Welcome."))


@component
def About():
    return div(h1("About"), p("A small routed app."))


@component
def User(params: Prop[dict], query: Prop[dict]):
    # ``params`` and ``query`` are Prop accessors. Navigating from /users/1
    # to /users/2 updates them in place; the component isn't remounted.
    return div(
        h1("User ", lambda: params()["user_id"]),
        p("Tab: ", lambda: query().get("tab", "info")),
    )


@component
def NotFound():
    return div(h1("Not found"), p(lambda: f"No page at {current_path()}"))


# Loaded on first visit; the import runs inside an async memo.
Team = lazy(lambda: ("app.about.team", "Page"))

routes = [
    Route("/", Home),
    Route("/about", About, children=[Route("team", Team)]),
    Route("/users/:user_id", User),
]


@component
def App():
    return div(
        nav(
            ul(
                li(Link("Home", href="/", end=True)),
                li(Link("About", href="/about")),
                li(Link("Team", href="/about/team", on_mouseenter=lambda e: Team.preload())),
                li(Link("User 1", href="/users/1?tab=posts")),
            ),
        ),
        main_(
            Errored(
                lambda: Loading(
                    lambda: Router(routes, not_found=NotFound),
                    fallback=p("Loading page..."),
                ),
                fallback=lambda err, reset: p("Page failed to load: ", str(err)),
                reset_on=current_path,
            ),
        ),
    )


render(App(), "#app")
```

## How it works

- [`Router`][wybthon.Router] reads [`current_path`][wybthon.current_path] and renders the component of the first matching [`Route`][wybthon.Route]. Only a change in *which* route matches re-mounts the outlet; param and query changes flow into the mounted component as prop updates.
- The matched component receives `params` and `query` as props. Both are dicts, so read them with `params()["user_id"]` inside a hole or memo. Outside the route component, [`use_params`][wybthon.use_params] and [`use_query`][wybthon.use_query] return the same accessors.
- [`Link`][wybthon.Link] renders an `<a>` that navigates with the History API. It adds `active_class` (default `"active"`) while its path matches; `end=True` requires an exact match, which keeps "Home" from being active everywhere. Modifier-key clicks and middle clicks pass through to the browser.
- Nested `Route.children` paths are joined with the parent path, so `Route("team", Team)` under `/about` matches `/about/team`.
- Wrapping the router in [`Loading`][wybthon.Loading] and [`Errored`][wybthon.Errored] with `reset_on=current_path` gives every page a loading state and an error state that clears on navigation.

## Programmatic navigation

```python
from wybthon import navigate

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
Router(routes, base_path="/app")
```

Inside the tree, [`use_base_path`][wybthon.use_base_path] returns the active base path.

## Wildcards

A trailing `/*` matches any remainder:

```python
Route("/docs/*", Docs)
```

## Next steps

- Read the [Router](../concepts/router.md) concept page.
- See [Async and Loading](../concepts/async-loading.md) for code-splitting routes.
- Browse the [`router`][wybthon.router] and [`router_core`][wybthon.router_core] APIs.
