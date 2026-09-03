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
| [`Dynamic`][wybthon.Dynamic] | `Dynamic(component, **props)`: render a tag or component chosen at runtime. |

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
- `Dynamic` accepts a tag name, a component, `None`, or an accessor
  returning one of those; the subtree remounts when the resolved
  component changes.

#### See also

- [`map_array`][wybthon.map_array] and [`create_selector`][wybthon.create_selector]: the engine behind `For` and per-row selection
- [Concepts: Components](../concepts/components.md)
- [Guides: Authoring patterns](../guides/authoring-patterns.md)
- [Guides: Performance](../guides/performance.md)
