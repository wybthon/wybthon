# Router

Routing with path params, search params, nested layouts, plain-anchor navigation, and preloading, as in Solid Router 2.0. Import it from `wybthon.router`; its names aren't exported from the top-level `wybthon` package.

```python
from wybthon import Children, component, html
from wybthon.router import Route, create_router


@component
def Home():
    return html(t"<h1>Home</h1>")


@component
def User(params: dict[str, str]):
    return html(t"<h1>User {params['id']}</h1>")


@component
def NotFound():
    return html(t"<h1>Not found</h1>")


@component
def Shell(children: Children = None):
    return html(t"""
      <nav><a href="/">Home</a> <a href="/users/1">Ada</a></nav>
      <main>{children}</main>
    """)


router = create_router(
    [
        Route("/", Home),
        Route("/users/:id", User),
        Route("*404", NotFound),
    ]
)


def app():
    return router(root=Shell)
```

- [`create_router(routes, *, base="", preload_links=True)`][wybthon.router.create_router] makes the router from its route tree. Call it once, at module level, and call the result to render it.
- `router(root=Shell)` renders the matched route inside `Shell`, a root layout that stays mounted on every page and receives the route as its `children` parameter. `router()` renders the route alone.
- [`Route(path, component, children=[], preload=None)`][wybthon.router.Route] maps a pattern to a component.
- Links are plain `<a href>` elements (see [Links](#links)).
- [`navigate(path, *, replace=False, scroll=True)`][wybthon.router.navigate] changes the URL from code.

## Patterns

| Pattern | Matches | Params |
| --- | --- | --- |
| `/users` | `/users`, `/users/` | `{}` |
| `/users/:id` | `/users/42` | `{"id": "42"}` |
| `/posts/:page?` | `/posts`, `/posts/2` | `{"page": ""}`, `{"page": "2"}` |
| `/docs/*rest` | `/docs`, `/docs/a/b` | `{"rest": ""}`, `{"rest": "a/b"}` |
| `*404` | anything | `{"404": "the/path"}` |

A bare `*` captures into `params["wildcard"]`. A catch-all must be a pattern's last segment. When several routes match, literals win over parameters, which win over catch-alls, so a `*404` route can sit anywhere in the list. Parameter values are URL-decoded.

When no route matches, the router renders nothing, and a server render answers with status 404. A catch-all route is the not-found page; call [`http_status`][wybthon.http_status] in it to say so explicitly.

## Params and search params

A route's component declares the route props it needs as parameters. There are four:

| Parameter | Value |
| --- | --- |
| `params: dict[str, str]` | The matched path parameters. |
| `search: SearchParams` | The parsed query string, a [`SearchParams`][wybthon.router.SearchParams] (import it from `wybthon.router`). |
| `data: Any` | What the route's `preload` returned, once it resolved. |
| `children: Children` | The matched child route, for a layout. |

The router passes only the ones the component declares, so `User` above takes `params` alone, and a route component that needs none of them, like `Home`, takes no parameters. A [`lazy`][wybthon.lazy] component gets the same filtering once its code has loaded.

They're ordinary props: `params["id"]` is a tracked read of the current value. `params` and `search` update in place: navigating from `/users/1` to `/users/2` pushes a new `params` value into the mounted component instead of remounting it, so its local state survives.

```python
Route("/users/:id", User)
# /users/42?tab=activity -> params["id"] == "42", search["tab"] == "activity"
```

Read them where they can update: in the template (`{params['id']}` is dynamic, so the compiler makes it a getter), or in a memo, an effect, or an async memo's body. Reading one at the top level of the component body reads it once, and dev mode warns.

A route component can declare parameters of its own too, as long as they have defaults, since the router never passes them:

```python
@component
def User(params: dict[str, str], show_avatar: bool = True):
    return html(t"<h1>User {params['id']}</h1>")
```

`SearchParams` is a `dict` of each name's last value; `search.get_all("tag")` keeps repeated parameters in URL order.

Any component under the router can read the same state with these functions:

| Function | Returns |
| --- | --- |
| [`use_params()`][wybthon.router.use_params] | The path parameters, a mapping whose reads are tracked: `use_params()["id"]` (empty outside a router). |
| [`use_search_params()`][wybthon.router.use_search_params] | `(search, set_search)`: the query's parameters, a mapping whose reads are tracked, and a setter. |
| [`use_location()`][wybthon.router.use_location] | The URL; read `.path`, `.search`, `.hash` (decoded), `.query`, or `.href`, each tracked. |
| [`use_route_matches()`][wybthon.router.use_route_matches] | A tracked accessor for the routes the URL shows, root to leaf. |

`set_search` merges its changes into the query string and navigates without scrolling; `None` or `""` removes a key:

```python
@component
def Pager():
    search, set_search = use_search_params()

    def next_page():
        set_search(page=int(search.get("page", "1")) + 1)

    return html(t"<button onclick={next_page}>Next</button>")
```

## Nested routes and layouts

A route with `children` is a layout. Child paths continue the parent's path, even when they start with `/`, as in Solid. The layout renders when one of its children matches, with that child as its `children` prop; [`Outlet()`][wybthon.router.Outlet] renders the same thing anywhere in the layout. Only a change in *which* route matches remounts it, so a layout stays mounted while its children change.

```python
@component
def UserLayout(params: dict[str, str], children: Children):
    return html(t"""
      <section>
        <h1>User {params["id"]}</h1>
        <nav><a href="/users/{params["id"]}">Overview</a> <a href="/users/{params["id"]}/settings">Settings</a></nav>
        {children}
      </section>
    """)


router = create_router(
    [
        Route(
            "/users/:id",
            UserLayout,
            children=[
                Route("/", UserOverview),
                Route("/settings", UserSettings),
            ],
        ),
    ]
)
```

A layout doesn't match on its own: `/users/1` matches here because of the `Route("/")` child. A route with no component groups its children under a path without rendering anything of its own: `Route("/admin", children=[...])`.

## Links

Write links as plain anchors. When the user clicks a same-origin link under the router's base path, the router navigates with the History API instead of loading a page. It leaves the click to the browser when:

- a modifier key is held, or the button isn't the primary one;
- the link has a `target` (other than `_self`), `download`, or `rel="external"`;
- the link goes to another origin, outside the base path, or only to a `#fragment`;
- a handler called `event.prevent_default()`.

Hrefs are ordinary URLs: a path starting with `/` is a full path, and the router's `base` isn't added to it.

[`use_link_state(href, *, end=False)`][wybthon.router.use_link_state] says whether a link is active, for styling navigation. `active()` is true on the link's path and below it (only on the path itself with `end=True`); the base path only matches exactly. `current()` is true when the path and the query both match, which is what `aria-current="page"` means:

```python
@component
def NavLink(href: str, children: Children = None):
    state = use_link_state(lambda: href)
    return html(t"""
      <a href={href} class={"active" if state.active() else ""} aria-current={"page" if state.current() else None}>
        {children}
      </a>
    """)
```

## Preloading

A route's `preload` runs when the route is about to show, and when the pointer rests on (or focus moves to) a link to it, so its data is already loading by the time the user clicks. It receives [`PreloadArgs`][wybthon.router.PreloadArgs] with the matched `params`, the `location`, and the `intent`: `"initial"`, `"navigate"`, or `"preload"`. Warm the route's [queries](full-stack.md#queries) there:

```python
from wybthon.router import PreloadArgs, query


@query
async def get_user(user_id: int) -> User:
    return await fetch_user(user_id)


def preload_user(args: PreloadArgs):
    return get_user(int(args.params["id"]))


router = create_router([Route("/users/:id", User, preload=preload_user)])
```

Whatever `preload` returns becomes the component's `data` prop; when it's awaitable, the router holds the navigation until it resolves, and `data` is its result. A lazily loaded component (see [`lazy`][wybthon.lazy]) starts loading at the same moments. [`preload_route(href)`][wybthon.router.preload_route] preloads a route from code. Pass `preload_links=False` to `create_router` to preload only on navigation.

## Async routes

Navigating to a route whose data or code is still loading is a transition: the old page stays on screen, consistent, until the new one is ready. Put a [`Loading`][wybthon.Loading] boundary around the router (or inside a layout) for the first load, which has nothing to hold:

```python
def app():
    return Loading(router(root=Shell), fallback=html(t"<p>Loading...</p>"))
```

## File routes

[`file_routes(package)`][wybthon.router.file_routes] builds the route tree from a package of modules, one per page. See [File routes](full-stack.md#file-routes).

```python
router = create_router(file_routes("app.routes"))
```

## Matching without a browser

[`match_route(routes, pathname, base_path="")`][wybthon.router.match_route] returns `(route, {"params": ..., "matches": [...]})`, or `None`, and needs no browser, so it runs in tests and tools. Any object with a `path` and `children` works as a route, including [`RouteSpec`][wybthon.router.RouteSpec]. [`router.match(href)`][wybthon.router.Router.match] returns the routes a URL shows, root to leaf.

```python
from wybthon.router import RouteSpec, match_route

routes = [RouteSpec("/"), RouteSpec("/users", children=[RouteSpec("/:id")]), RouteSpec("/docs/*")]
match_route(routes, "/users/42")  # (RouteSpec(path='/:id'), {"params": {"id": "42"}, "matches": [...]})
match_route(routes, "/missing")  # None
```

## On the server

A server render routes by the request's URL ([`render_to_stream(view, url=...)`][wybthon.server.render_to_stream], or the request [`wybthon.asgi`][wybthon.asgi] is answering). `navigate` does nothing there. Outside a browser (in tests), `navigate` updates the URL signal without touching history; call [`flush`][wybthon.flush] afterward.

## See also

- [Full-stack apps](full-stack.md): queries, form actions, server functions, and file routes
- [Async and loading](async-loading.md): `Loading` boundaries and transitions
- [API: `wybthon.router`](../api/router.md)
