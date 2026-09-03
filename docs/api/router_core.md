### wybthon.router_core

::: wybthon.router_core

#### What's in this module

`router_core` is the browser-agnostic matcher behind
[`wybthon.router`](router.md). It compiles route patterns to regular
expressions, matches them against a pathname, and picks the most
specific match. It has no browser dependency, so it runs in unit tests,
tooling, and on a server.

| Name | Description |
| --- | --- |
| [`resolve`][wybthon.router_core.resolve] | `resolve(routes, pathname, base_path="")` returns `(route, {"params": {...}})` or `None`. |
| [`RouteSpec`][wybthon.router_core.RouteSpec] | Minimal `path` plus `children` dataclass for pure-Python tests; any object with those attributes works, including [`Route`][wybthon.Route]. |

#### Path patterns

| Pattern | Matches | Params |
| --- | --- | --- |
| `/users` | `/users` | `{}` |
| `/users/:id` | `/users/42` | `{"id": "42"}` |
| `/docs/*` | `/docs`, `/docs/intro`, `/docs/a/b` | `{"wildcard": None}` or `{"wildcard": "intro"}` |
| `/files/*/raw` | `/files/a/b/raw` | `{"wildcard": "a/b"}` |

Nested `children` join their paths with the parent's (a child path
starting with `/` is absolute). When several routes match, the longest
full pattern wins. `base_path` is stripped before matching; a pathname
outside the base returns `None`.

```python
from wybthon.router_core import RouteSpec, resolve

routes = [
    RouteSpec("/"),
    RouteSpec("/users", children=[RouteSpec(":id")]),
    RouteSpec("/docs/*"),
]

resolve(routes, "/users/42")            # (RouteSpec(path=':id', ...), {"params": {"id": "42"}})
resolve(routes, "/docs/intro/setup")    # (..., {"params": {"wildcard": "intro/setup"}})
resolve(routes, "/app/users/7", base_path="/app")
resolve(routes, "/missing")             # None
```

Param values are the raw matched segments; the browser router decodes
query strings separately.

#### See also

- [Router](router.md): `Route`, `Router`, `Link`, and navigation
- [Concepts: Router](../concepts/router.md)
- [Examples: Router](../examples/router.md)
