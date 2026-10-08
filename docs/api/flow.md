### wybthon.flow

::: wybthon.flow

#### What's in this module

Control-flow primitives that create isolated reactive scopes, so only
the relevant subtree updates when a condition or list changes. Each is a
function returning a component `VNode`; conditions and sources are
accessors (or plain values), and `children` and `fallback` slots are
VNodes or callables evaluated inside the primitive's own scope. All
arguments are positional except the keyword-only options noted below.

| Name | Description |
| --- | --- |
| [`Show`][wybthon.Show] | `Show(when, children, fallback=None, *, keyed=False)`: render one branch by truthiness. |
| [`For`][wybthon.For] | `For(each, children, fallback=None, *, keyed=True)`: one cached row per item; rows move, never re-diff. |
| [`Repeat`][wybthon.Repeat] | `Repeat(count, children, fallback=None, *, start=0)`: `children(i)` for `i` in `range(start, start + count)`. |
| [`Switch`][wybthon.Switch] / [`Match`][wybthon.Match] | `Switch(Match(when, children, keyed=False), ..., fallback=None)`: first truthy branch wins. |
| [`dynamic`][wybthon.dynamic] | `dynamic(source)`: a component whose implementation (a component or tag) is chosen by a reactive `source`. Call the result with children and props. |
| [`client_only`][wybthon.client_only] | `client_only(children, *, fallback=None)`: render `children` only in the browser, after hydration; `fallback` renders on the server. |
| [`NoHydration`][wybthon.NoHydration] | `NoHydration(*children)`: server-rendered HTML the browser keeps as static DOM instead of hydrating. |
| [`Hydration`][wybthon.Hydration] | `Hydration(*children, id=None)`: a passthrough kept for parity with Solid 2.0. |
| [`is_hydrating`][wybthon.is_hydrating] | `True` only during the synchronous mount of [`hydrate`][wybthon.hydrate]. |

#### `For` keying shapes

`keyed` selects how rows are matched between updates, and with it the
callback shape:

| `keyed` | Rows match by | `children(item, index)` receives |
| --- | --- | --- |
| `True` (default) | Identity (scalars by value) | the raw item, `Accessor[int]` |
| `False` | Position | `Accessor[T]`, `int` |
| `key(item)` callable | The key; a new object with the same key updates the row in place | `Accessor[T]`, `Accessor[int]` |

The row callback runs once per row inside the row's owner scope and
untracked; anything reactive inside a row must read an accessor within
a hole, memo, or effect. Passing a plain list for `each` renders once
and warns in dev mode.

```python
from wybthon import For, Match, Repeat, Show, Switch, create_signal, li, p, span, ul

todos, set_todos = create_signal([{"id": 1, "title": "Ship", "done": False}])
status, set_status = create_signal("ready")
rating, set_rating = create_signal(3)
user, set_user = create_signal(None)

view = ul(
    Show(user, lambda u: li("Hello, ", lambda: u()["name"]), fallback=li("Sign in")),
    For(todos, lambda todo, i: li(lambda: f"{i() + 1}. {todo['title']}")),
    For(todos, lambda todo, i: li(lambda: todo()["title"]), keyed=lambda t: t["id"]),
    li(Repeat(rating, lambda i: span("*"), start=1)),
    Switch(
        Match(lambda: status() == "loading", lambda: p("Loading...")),
        Match(lambda: status() == "ready", lambda: p("Ready")),
        fallback=lambda: p("Unknown"),
    ),
)
```

- `Show` tracks only the truthiness of `when`; a callable `children`
  may take the value accessor (or the raw value with `keyed=True`, which
  re-creates the branch on every change).
- `Repeat` is driven purely by the count: growing mounts tail slots,
  shrinking disposes them, and nothing else is touched. `count` and
  `start` may be accessors or ints.
- `dynamic` accepts a tag name, a component, `None`, or an accessor
  returning one of those; each instance remounts when the resolved
  component changes.
- `client_only` renders its fallback during a server render and while
  hydrating, then its children; see
  [Server rendering](../concepts/server-rendering.md).
- `NoHydration` costs no Python work while hydrating: the kernel keeps
  the region's server DOM as is (`CLAIM_STATIC`) and nothing inside it
  mounts or updates. In a page that wasn't server-rendered, its
  children render normally.

#### See also

- [`map_array`][wybthon.map_array] and [`repeat`][wybthon.repeat]: the reactive mapping behind `For` and `Repeat`
- [`create_projection`][wybthon.create_projection]: per-row selection that notifies only the changed rows
- [Concepts: Components](../concepts/components.md)
- [Guides: Authoring patterns](../guides/authoring-patterns.md)
- [Guides: Performance](../guides/performance.md)
