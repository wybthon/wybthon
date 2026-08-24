### wybthon.flow

::: wybthon.flow

#### What's in this module

`flow` provides SolidJS-style reactive flow control components. They
create *isolated reactive scopes* so that only the relevant subtree
re-renders when the tracked condition or list changes.

| Component | Use it for |
| --- | --- |
| [`Show`][wybthon.Show] | Conditional rendering with a single fallback. |
| [`For`][wybthon.For] | List rendering with stable per-item scopes and a choice of keying modes. |
| [`Repeat`][wybthon.Repeat] | Count-driven rendering (`children(i)` for each index), with no diffing. |
| [`Switch`][wybthon.Switch] / [`Match`][wybthon.Match] | Multi-branch conditional rendering. |
| [`Dynamic`][wybthon.Dynamic] | Render a component chosen at runtime. |

#### Idioms

```python
from wybthon import (
    For, Match, Repeat, Show, Switch, component, create_signal,
)
from wybthon.html import li, p, span, ul


@component
def Demo():
    items, _ = create_signal(["a", "b", "c"])
    is_logged_in, _ = create_signal(False)
    rating, _ = create_signal(3)

    return ul(
        Show(
            when=is_logged_in,
            children=lambda: li("Welcome!"),
            fallback=lambda: li("Please log in"),
        ),
        For(each=items, children=lambda item, idx: li(item())),
        li(Repeat(times=rating, children=lambda i: span("*"))),
    )
```

- Pass *getters* (the signal accessor itself) to `when` / `each` /
  `times`.
- `children` may be a `VNode`, a callable returning a `VNode`, the
  per-item mapping callback for `For`, or the per-index callback for
  `Repeat`.
- In every `For` mode the callback receives
  `(item_getter, index_getter)`; call `item()` for the current value,
  or pass the getter itself where the value should stay live.

##### `For` keying modes

`For(each=..., children=..., fallback=..., key=...)` matches rows to
items in one of three ways:

- `key=None` (default): rows match by **reference identity**. The same
  object keeps its row; a replacement object makes a new row.
- `key=callable`: rows match by `key(item)`. A fresh object with the
  same key **updates the existing row in place** through the `item`
  getter; ideal for data refreshed from a server.
- `key="index"`: rows match by **position**. Each index slot renders
  once, and its `item` getter updates when the value at that position
  changes (this replaces the old `Index` component).

In all modes the mapping callback runs **once per row** and the
resulting subtree is cached: list changes mount added rows, dispose
removed ones, and move existing DOM for reorders. When a row leaves the
list, its reactive scope (including any effects or cleanups created
inside the callback) is disposed.

##### `Repeat`

`Repeat(times=..., children=..., fallback=...)` renders `children(i)`
for each index in `range(times)`. Rendering is driven purely by the
count: growing it mounts new tail slots, shrinking it disposes excess
tail slots, and nothing else is touched. Use it for pagination dots,
star ratings, skeleton rows, and other count-driven UI where list
diffing is pure overhead.

#### See also

- [Concepts → Components](../concepts/components.md)
- [Authoring patterns](../guides/authoring-patterns.md)
- [`map_array`][wybthon.map_array] / [`index_array`][wybthon.index_array]
  for reactive list mapping outside of `For` / `Repeat`.
