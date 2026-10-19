### wybthon.flow

::: wybthon.flow

#### What's in this module

Control-flow primitives that create isolated reactive scopes, so only
the relevant subtree updates when a condition or list changes.
Conditions and sources are accessors (or plain values), and `children`
and `fallback` slots are nodes or callables evaluated inside the
primitive's own scope. All arguments are positional except the
keyword-only options noted below.

`Show`, `For`, `Repeat`, and `Switch` mount as native **regions**, not
wrapper components: each is one computation that selects what to
render, plus an owned scope per branch or row. There's no component
context or props object. When a reactive hole re-renders and returns
the same kind of region in the same place, the new condition or source
is pushed into the mounted region, so branches and rows that are still
selected survive.

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
and warns in dev mode. A store list can be passed as is.

#### Typed callbacks

`For` and `Show` have generic overloads, so type checkers infer the
callback's parameters from the source (`Repeat`'s callback is typed as
taking an `int`):

| Call | Inferred parameters |
| --- | --- |
| `For(todos, lambda todo, i: ...)` | `todo: Todo`, `i: Accessor[int]` |
| `For(todos, lambda todo, i: ..., keyed=False)` | `todo: Accessor[Todo]`, `i: int` |
| `For(todos, lambda todo, i: ..., keyed=lambda t: t.id)` | `todo: Accessor[Todo]`, `i: Accessor[int]` |
| `Show(user, lambda u: ...)` | `u: Accessor[User]` |
| `Show(user, lambda u: ..., keyed=True)` | `u: User` |

The callbacks here are arguments to `For` and `Show`, not template
interpolations, so they may be bare lambdas. Inside a t-string, wrap a
lambda in parentheses or give it a name.

```python
from wybthon import For, Match, Repeat, Show, Switch, create_signal, html

todos, set_todos = create_signal([{"id": 1, "title": "Ship", "done": False}])
status, set_status = create_signal("ready")
rating, set_rating = create_signal(3)
user, set_user = create_signal(None)


def greeting(u):
    return html(t"<li>Hello, {(lambda: u()['name'])}</li>")


def numbered(todo, i):
    return html(t"<li>{(lambda: i() + 1)}. {todo['title']}</li>")


def live_title(todo, i):
    return html(t"<li>{(lambda: todo()['title'])}</li>")


def is_loading():
    return status() == "loading"


def is_ready():
    return status() == "ready"


view = html(t"""
  <ul>
    {Show(user, greeting, fallback=html(t"<li>Sign in</li>"))}
    {For(todos, numbered)}
    {For(todos, live_title, keyed=lambda t: t["id"])}
    <li>{Repeat(rating, lambda i: html(t"<span>*</span>"), start=1)}</li>
    {
    Switch(
        Match(is_loading, html(t"<li>Loading...</li>")),
        Match(is_ready, html(t"<li>Ready</li>")),
        fallback=html(t"<li>Unknown</li>"),
    )
}
  </ul>
""")
```

- `Show` tracks only the truthiness of `when`; a callable `children`
  may take the value accessor (or the raw value with `keyed=True`, which
  re-creates the branch on every change). `Show` and `Switch` are one
  branch computation that re-mounts only when the selected branch
  changes.
- `children` and `fallback` may be nodes, such as templates, or
  callables. A node branch is mounted afresh each time it's selected.
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
