### wybthon.router

::: wybthon.router

#### What's in this module

A client-side router built on the History API, plus the pure path
matcher behind it. Import it from `wybthon.router`; these names aren't
re-exported from `wybthon`. Only a change in *which* route matches
remounts the outlet; param and query changes flow into the mounted
component as prop updates, so navigating from `/users/1` to `/users/2`
keeps the same component instance.

| Name | Description |
| --- | --- |
| [`Route`][wybthon.router.Route] | `Route(path, component, children=[], preload=None)`; patterns support `:param` and a `*` wildcard. `preload(params)` warms data before the route shows. |
| [`RouteProps`][wybthon.router.RouteProps] | `Props` for a routed component: `params: Prop[dict[str, str]]` and `query: Prop[QueryParams]`. Subclass it to add fields. |
| [`Router`][wybthon.router.Router] | `Router(routes, *, base_path="", not_found=None)`; renders the matched component with `params` and `query` props. |
| [`Outlet`][wybthon.router.Outlet] | Renders the next matched child route inside a parent route's layout. |
| [`Link`][wybthon.router.Link] | `Link(*children, href="/", replace=False, active_class="active", end=False, **rest)`; an `<a>` that navigates and marks itself active. |
| [`navigate`][wybthon.router.navigate] | `navigate(path, *, replace=False, scroll=True)`; push or replace a history entry and update `current_path`. |
| [`current_path`][wybthon.router.current_path] | Accessor for the pathname plus query string; updated by `navigate` and `popstate`. |
| [`use_params`][wybthon.router.use_params] | Accessor for the matched route's params dict (`{}` outside a router). |
| [`use_query`][wybthon.router.use_query] | Accessor for the parsed [`QueryParams`][wybthon.router.QueryParams] (empty outside a router). |
| [`use_hash`][wybthon.router.use_hash] | Accessor for the decoded URL fragment, without its `#`. |
| [`use_base_path`][wybthon.router.use_base_path] | The surrounding router's base path (`""` outside one). |
| [`preload`][wybthon.router.preload] | `preload(path)`: warm a route's lazy component and data through the surrounding router. |
| [`QueryParams`][wybthon.router.QueryParams] | A `dict` of the last value per key, plus `get_all(key)` for repeated keys. |
| [`resolve`][wybthon.router.resolve], [`RouteSpec`][wybthon.router.RouteSpec] | The browser-independent matcher, usable in tests, tools, and on a server. |

```python
from wybthon import component, html, http_status
from wybthon.router import Link, Outlet, Route, RouteProps, Router


@component
def Home():
    return html(t"<h1>Home</h1>")


@component
def Users():
    return html(t"<div><h1>Users</h1>{Outlet()}</div>")  # child routes render here


@component
def User(props: RouteProps):
    def user_id():
        return props.params()["id"]

    def tab():
        return props.query().get("tab", "info")

    return html(t"<h1>User {user_id} (tab={tab})</h1>")


@component
def NotFound(props: RouteProps):
    http_status(404)  # sets the status during a server render
    return html(t"<h1>Not found</h1>")


routes = [Route("/", Home), Route("/users", Users, children=[Route(":id", User)]), Route("/docs/*", Home)]


@component
def App():
    return html(t"""
      <div>
        <nav>
          {Link("Home", href="/", end=True)}
          {Link("Ada", href="/users/1?tab=posts")}
        </nav>
        {Router(routes, base_path="/app", not_found=NotFound)}
      </div>
    """)
```

- A trailing `/*` captures the rest into `params["wildcard"]` and also
  matches the parent path (`/docs/*` matches `/docs`). Nested `children`
  routes join their paths with the parent's; the parent renders the
  child through `Outlet()`.
- `Link` joins `href` with the router's `base_path` unless it starts with
  `http://`, `https://`, or `#`. Modifier-key and middle clicks fall
  through to the browser. `end=True` makes the active class exact-match
  only. A `Link`'s own `on_click` receives the event. Call it inside a
  template interpolation (`{Link("Home", href="/")}`) or use the tag
  form (`<{Link} href="/">Home</{Link}>`).
- Outside a browser, `navigate` only updates the `current_path` signal,
  and during a server render it's a no-op; call
  [`flush`][wybthon.flush] afterward in tests.

#### Path matching

[`resolve(routes, pathname, base_path="")`][wybthon.router.resolve]
returns `(route, {"params": {...}, "matches": [...]})` or `None`, where
`matches` lists the matched route and its ancestors. Any object with
`path` and `children` attributes works as a route, including
[`Route`][wybthon.router.Route] and the minimal
[`RouteSpec`][wybthon.router.RouteSpec].

| Pattern | Matches | Params |
| --- | --- | --- |
| `/users` | `/users` | `{}` |
| `/users/:id` | `/users/42` | `{"id": "42"}` |
| `/docs/*` | `/docs`, `/docs/intro`, `/docs/a/b` | `{"wildcard": ""}` or `{"wildcard": "intro"}` |
| `/files/*/raw` | `/files/a/b/raw` | `{"wildcard": "a/b"}` |

Nested `children` join their paths with the parent's (a child path
starting with `/` is absolute). When several routes match, the most
specific pattern wins. `base_path` is stripped before matching; a
pathname outside the base returns `None`.

```python
from wybthon.router import RouteSpec, resolve

routes = [
    RouteSpec("/"),
    RouteSpec("/users", children=[RouteSpec(":id")]),
    RouteSpec("/docs/*"),
]

resolve(routes, "/users/42")  # (RouteSpec(path=':id', ...), {"params": {"id": "42"}, "matches": [...]})
resolve(routes, "/docs/intro/setup")  # (..., {"params": {"wildcard": "intro/setup"}, ...})
resolve(routes, "/app/users/7", base_path="/app")
resolve(routes, "/missing")  # None
```

Param values are the raw matched segments; the browser router decodes
query strings separately.

#### See also

- [Lazy loading](lazy.md): code-split route components
- [Request](request.md): `http_status` and `http_header` for not-found and redirect responses
- [Concepts: Router](../concepts/router.md)
- [Examples: Router](../examples/router.md)
