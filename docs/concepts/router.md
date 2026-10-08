# Router

Client-side routing with path params, query parsing, nested routes, and
active links. Import the router from `wybthon.router`; its names aren't
exported from the top-level `wybthon` package.

```python
from wybthon import component, div, h1, nav
from wybthon.router import Link, Route, RouteProps, Router


@component
def Home():
    return h1("Home")


@component
def User(props: RouteProps):
    return h1("User ", lambda: props.params()["id"])


@component
def App():
    return div(
        nav(Link("Home", href="/"), Link("Ada", href="/users/1")),
        Router([Route("/", Home), Route("/users/:id", User)]),
    )
```

- [`Router(routes, *, base_path="", not_found=None)`][wybthon.router.Router] renders the component of the route matching [`current_path`][wybthon.router.current_path].
- [`Route(path, component, children=[], preload=None)`][wybthon.router.Route] maps a pattern to a component.
- [`Link`][wybthon.router.Link] renders an anchor that navigates with the History API and marks itself active.
- [`navigate(path, *, replace=False, scroll=True)`][wybthon.router.navigate] changes the URL programmatically.

## Params and query

A routed component declares its inputs with
[`RouteProps`][wybthon.router.RouteProps], which has two reactive fields:
`params: Prop[dict[str, str]]` and `query: Prop[QueryParams]`. Both
update in place: navigating from `/users/1` to `/users/2` pushes a new
`params` value into the mounted component instead of remounting it, so
local state survives. A route component that doesn't need them can take
no parameters, like `Home` above.

```python
Route("/users/:id", User)
# /users/42?tab=activity -> props.params()["id"] == "42", props.query()["tab"] == "activity"
```

Subclass `RouteProps` to add fields of your own, with defaults, since
the router passes only `params` and `query`:

```python
from wybthon import Prop, prop
from wybthon.router import RouteProps


class UserProps(RouteProps):
    show_avatar: Prop[bool] = prop(default=True)
```

Query values are URL-decoded strings in a
[`QueryParams`][wybthon.router.QueryParams] dict.
`query().get_all("tag")` preserves repeated parameters; ordinary lookup
returns the last value. [`use_hash()`][wybthon.router.use_hash] returns
a reactive decoded fragment. Any component under the router (not only
the matched one) can read the same accessors with
[`use_params`][wybthon.router.use_params] and
[`use_query`][wybthon.router.use_query], and the router's base path with
[`use_base_path`][wybthon.router.use_base_path]:

```python
from wybthon import component, p
from wybthon.router import use_params, use_query


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
are merged into `params`. A parent component renders
[`Outlet()`][wybthon.router.Outlet] where its matched child belongs.
Parent layouts stay mounted while child routes change:

```python
from wybthon import component, div, h1
from wybthon.router import Outlet


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
            Route("team/:name", Team),  # matches /about/team/ada
        ],
    ),
]
```

## Wildcards and not found

A trailing `*` matches the rest of the path (and the parent path itself)
into `params()["wildcard"]`:

```python
Route("/docs/*", Docs)  # /docs and /docs/guide/intro both match
```

When nothing matches, the router renders `not_found` (a component that
also receives `params` and `query`) or, if none is given, a literal
"Not Found" `<div>`. During a server render, the not-found component can
set the response status with [`http_status`][wybthon.http_status]:

```python
from wybthon import component, h1, http_status


@component
def NotFound():
    http_status(404)  # ignored in the browser
    return h1("Not found")


Router(routes, not_found=NotFound)
```

## Base path

Pass `base_path` when the app is served under a prefix. It's stripped
before matching, and every `Link` beneath the router prepends it:

```python
Router(routes, base_path="/app")
Link("About", href="/about")  # renders href="/app/about"
```

Hrefs starting with `http://`, `https://`, or `#` are left alone.

## Links

```python
Link("Users", href="/users", class_="nav-link")
Link("Users", href="/users", end=True)  # active only on an exact match
Link("Settings", href="/settings", replace=True)  # replace the history entry
Link("Home", href="/", active_class="is-current")  # custom active class
Link("Home", href="/", active_class=None)  # no active class
```

- The link is active when the current path equals its target, or starts with it as a path prefix unless `end=True`. The active class (default `"active"`) is merged with any `class_` you pass.
- Clicks with a modifier key (Cmd, Ctrl, Shift) or a non-primary button are passed through to the browser so users can open links in new tabs.
- `href` may be an accessor for links whose target changes.
- Other keyword arguments (`aria_label`, `on_click`, `data_*`) are forwarded to the `<a>` element. A user `on_click` receives the event and runs before the router's navigation.

## Programmatic navigation

```python
from wybthon.router import current_path, navigate

navigate("/about")  # pushState
navigate("/about", replace=True)  # replaceState
current_path()  # "/about" (an accessor: pathname, query string, and hash)
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
from wybthon import Loading, lazy, p
from wybthon.router import Link, Route, Router

Docs = lazy(lambda: ("app.docs.page", "Page"))
About = lazy(lambda: ("app.about.page", "Page"))

routes = [
    Route("/docs/*", Docs),
    Route("/about", About),
]

Loading(lambda: Router(routes), fallback=p("Loading page..."))
Link("About", href="/about")  # warms About's code on hover or focus
```

Notes for Pyodide:

- The module must be present in the Pyodide filesystem or installed with `micropip` before the loader imports it; an async loader can `await micropip.install(...)` first.
- Links call the matching route's `.preload()` on hover and focus to hide the load time before navigation. Call `About.preload()`, or [`preload("/about")`][wybthon.router.preload] under a router, to warm a page from anywhere else.

## Recovering from page errors

Pair the router with [`Errored`][wybthon.Errored] and reset the boundary
when the route changes, so a broken page recovers as soon as the user
navigates away. The fallback's `err` is an accessor for the exception:

```python
from wybthon import Errored, p
from wybthon.router import Router, current_path

Errored(
    lambda: Router(routes),
    fallback=lambda err, reset: p(t"This page failed: {err}"),
    reset_on=current_path,
)
```

## Next steps

- Walk through the [Router example](../examples/router.md).
- See [Async and loading](async-loading.md) for code-splitting.
- Browse the [`router`](../api/router.md) API reference.

## Navigation intent and scroll

A `Route(..., preload=callback)` can warm data using its decoded parameter dict. The callback can be async. Links preload matching route code and data on hover or focus; navigation waits on the same cached work. Preload entries are bounded and canceled when the router is disposed. Failed entries are evicted for retry.

Static path segments take precedence over parameters, which take precedence over wildcards. Base paths match segment boundaries, so `/app` doesn't match `/application`. Parameters are percent-decoded, and trailing slashes normalize. [`resolve`][wybthon.router.resolve] runs the same matcher without a browser, on [`RouteSpec`][wybthon.router.RouteSpec] trees or `Route` lists, for tests, tools, and the server.

Modified clicks, download links, explicit targets, already-prevented events, and external URLs keep normal browser behavior. `navigate(..., scroll=False)` opts out of scroll handling. Normal navigation scrolls to a hash target or the top after commit; back/forward restores the recorded position for that URL. Multiple history entries for the same URL share that recorded position.
