# Router

Client-side routing with path params, query parsing, nested routes, and
active links.

```python
from wybthon import Link, Outlet, Prop, Route, Router, component
from wybthon.html import div, h1, nav


@component
def Home():
    return h1("Home")


@component
def User(params: Prop[dict], query: Prop[dict]):
    return h1("User ", lambda: params()["id"])


@component
def App():
    return div(
        nav(Link("Home", href="/"), Link("Ada", href="/users/1")),
        Router([Route("/", Home), Route("/users/:id", User)]),
    )
```

- [`Router(routes, *, base_path="", not_found=None)`][wybthon.Router] renders the component of the route matching [`current_path`][wybthon.current_path].
- [`Route(path, component, children=[])`][wybthon.Route] maps a pattern to a component.
- [`Link`][wybthon.Link] renders an anchor that navigates with the History API and marks itself active.
- [`navigate(path, *, replace=False)`][wybthon.navigate] changes the URL programmatically.

## Params and query

The matched component receives `params` and `query` as props. Both are
accessors for dicts, and both update in place: navigating from
`/users/1` to `/users/2` pushes a new `params` value into the mounted
component instead of remounting it, so local state survives.

```python
Route("/users/:id", User)
# /users/42?tab=activity -> params()["id"] == "42", query()["tab"] == "activity"
```

Query values are URL-decoded strings. `query().get_all("tag")` preserves repeated parameters; ordinary lookup returns the last value. `use_hash()` returns a reactive decoded fragment. Any component under the router
(not only the matched one) can read the same accessors with
[`use_params`][wybthon.use_params] and [`use_query`][wybthon.use_query],
and the router's base path with [`use_base_path`][wybthon.use_base_path]:

```python
from wybthon import component, use_params, use_query
from wybthon.html import p


@component
def Breadcrumb():
    params = use_params()
    query = use_query()
    return p(lambda: f"{params().get('slug', '')} | {query().get('page', '1')}")
```

Outside a router, `use_params()` and `use_query()` return accessors
yielding empty mappings, and `use_base_path()` returns `""`.

## Nested routes

Child routes join their paths to the parent's. Params from every level
are merged into `params`. A parent component renders `Outlet()` where its
matched child belongs. Parent layouts stay mounted while child routes change:

```python
@component
def About():
    return div(h1("About"), Outlet())
```

```python
routes = [
    Route(
        "/about",
        About,
        children=[
            Route("team/:name", Team),   # matches /about/team/ada
        ],
    ),
]
```

## Wildcards and not found

A trailing `*` matches the rest of the path (and the parent path itself)
into `params()["wildcard"]`:

```python
Route("/docs/*", Docs)   # /docs and /docs/guide/intro both match
```

When nothing matches, the router renders `not_found` (a component that
also receives `params` and `query`) or, if none is given, a literal
"Not Found" `<div>`:

```python
Router(routes, not_found=NotFound)
```

## Base path

Pass `base_path` when the app is served under a prefix. It's stripped
before matching, and every `Link` beneath the router prepends it:

```python
Router(routes, base_path="/app")
Link("About", href="/about")   # renders href="/app/about"
```

Hrefs starting with `http://`, `https://`, or `#` are left alone.

## Links

```python
Link("Users", href="/users", class_="nav-link")
Link("Users", href="/users", end=True)              # active only on an exact match
Link("Settings", href="/settings", replace=True)    # replace the history entry
Link("Home", href="/", active_class="is-current")   # custom active class
Link("Home", href="/", active_class=None)           # no active class
```

- The link is active when the current path equals its target, or starts with it as a path prefix unless `end=True`. The active class (default `"active"`) is merged with any `class_` you pass.
- Clicks with a modifier key (Cmd, Ctrl, Shift) or a non-primary button are passed through to the browser so users can open links in new tabs.
- `href` may be an accessor for links whose target changes.
- Other keyword arguments (`aria_label`, `on_click`, `data_*`) are forwarded to the `<a>` element. A user `on_click` runs before the router's navigation.

## Programmatic navigation

```python
from wybthon import current_path, navigate

navigate("/about")                 # pushState
navigate("/about", replace=True)   # replaceState
current_path()                     # "/about" (an accessor: pathname, query string, and hash)
```

`current_path` also updates on the browser's back and forward buttons.
Outside a browser (in tests), `navigate` only updates the signal; call
[`flush`][wybthon.flush] afterwards.

## Reactive route tables

`routes` may be an accessor returning a list of `Route`s, so a route
table can depend on the signed-in user or on feature flags. Only a
change in *which* route matches re-mounts the outlet.

## Lazy routes and preloading

Code-split heavy pages with [`lazy`][wybthon.lazy]. The loader returns a
module-path string, a `(module_path, attr)` tuple, a module, or a
component, and it may be async. While the module loads, the nearest
[`Loading`][wybthon.Loading] boundary shows its fallback.

```python
from wybthon import Link, Loading, Route, Router, lazy
from wybthon.html import p

Docs = lazy(lambda: ("app.docs.page", "Page"))
About = lazy(lambda: ("app.about.page", "Page"))

routes = [
    Route("/docs/*", Docs),
    Route("/about", About),
]

Loading(lambda: Router(routes), fallback=p("Loading page..."))
Link("About", href="/about", on_mouseover=lambda e: About.preload())
```

Notes for Pyodide:

- The module must be present in the Pyodide filesystem or installed with `micropip` before the loader imports it; an async loader can `await micropip.install(...)` first.
- Call `.preload()` on intent (hover, focus) to hide the load time before navigation.

## Recovering from page errors

Pair the router with [`Errored`][wybthon.Errored] and reset the boundary
when the route changes, so a broken page recovers as soon as the user
navigates away:

```python
from wybthon import Errored, Router, current_path
from wybthon.html import p

Errored(lambda: Router(routes), fallback=lambda err: p("This page failed"), reset_on=current_path)
```

## Next steps

- Walk through the [Router example](../examples/router.md).
- See [Async and loading](async-loading.md) for code-splitting.
- Browse the [`router`](../api/router.md) and [`router_core`](../api/router_core.md) API references.

## Navigation intent and scroll

A `Route(..., preload=callback)` can warm data using its decoded parameter dict. The callback can be async. Links preload matching route code and data on hover or focus; navigation waits on the same cached work. Preload entries are bounded and canceled when the router is disposed. Failed entries are evicted for retry.

Static path segments take precedence over parameters, which take precedence over wildcards. Base paths match segment boundaries, so `/app` doesn't match `/application`. Parameters are percent-decoded, and trailing slashes normalize.

Modified clicks, download links, explicit targets, already-prevented events, and external URLs keep normal browser behavior. `navigate(..., scroll=False)` opts out of scroll handling. Normal navigation scrolls to a hash target or the top after commit; back/forward restores the recorded position for that URL. Multiple history entries for the same URL share that recorded position.
