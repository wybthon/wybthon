### wybthon.router

::: wybthon.router

#### What's in this module

A client-side router built on the History API and the pure matcher in
[`router_core`](router_core.md). Only a change in *which* route matches
remounts the outlet; param and query changes flow into the mounted
component as prop updates, so navigating from `/users/1` to `/users/2`
keeps the same component instance.

| Name | Description |
| --- | --- |
| [`Route`][wybthon.Route] | `Route(path, component, children=[])`; patterns support `:param` and a trailing `*` wildcard. |
| [`Router`][wybthon.Router] | `Router(routes, *, base_path="", not_found=None)`; renders the matched component with `params` and `query` props. |
| [`Link`][wybthon.Link] | `Link(*children, href="/", replace=False, active_class="active", end=False, **rest)`; an `<a>` that navigates and marks itself active. |
| [`navigate`][wybthon.navigate] | `navigate(path, *, replace=False)`; push or replace a history entry and update `current_path`. |
| [`current_path`][wybthon.current_path] | Accessor for the pathname plus query string; updated by `navigate` and `popstate`. |
| [`use_params`][wybthon.use_params] | Accessor for the matched route's params dict (`{}` outside a router). |
| [`use_query`][wybthon.use_query] | Accessor for the parsed query-string dict (`{}` outside a router). |
| [`use_base_path`][wybthon.use_base_path] | The surrounding router's base path (`""` outside one). |

```python
from wybthon import Link, Prop, Route, Router, component, div, h1, nav, use_query

@component
def Home():
    return h1("Home")

@component
def User(params: Prop[dict]):
    query = use_query()
    return h1("User ", lambda: params()["id"], lambda: f" (tab={query().get('tab', 'info')})")

@component
def NotFound(params: Prop[dict]):
    return h1("Not found")

@component
def App():
    return div(
        nav(Link("Home", href="/", end=True), Link("Ada", href="/users/1?tab=posts")),
        Router(
            [Route("/", Home), Route("/users/:id", User), Route("/docs/*", Home)],
            base_path="/app",
            not_found=NotFound,
        ),
    )
```

- A trailing `/*` captures the rest into `params["wildcard"]` and also
  matches the parent path (`/docs/*` matches `/docs`). Nested `children`
  routes join their paths with the parent's; the most specific match
  wins.
- `Link` joins `href` with the router's `base_path` unless it starts with
  `http://`, `https://`, or `#`. Modifier-key and middle clicks fall
  through to the browser. `end=True` makes the active class exact-match
  only.
- Outside a browser, `navigate` only updates the `current_path` signal;
  call [`flush`][wybthon.flush] afterwards in tests.

#### See also

- [Router core](router_core.md): the matcher, usable without a browser
- [Lazy loading](lazy.md): code-split route components
- [Concepts: Router](../concepts/router.md)
- [Examples: Router](../examples/router.md)
