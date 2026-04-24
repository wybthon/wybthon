### wybthon.flow

::: wybthon.flow

#### What's in this module

`flow` provides SolidJS-style reactive flow control components. They
create *isolated reactive scopes* so that only the relevant subtree
re-renders when the tracked condition or list changes.

| Component | Use it for |
| --- | --- |
| [`Show`][wybthon.Show] | Conditional rendering with a single fallback. |
| [`For`][wybthon.For] | Keyed list rendering with stable per-item scopes. |
| [`Index`][wybthon.Index] | Index-keyed list rendering with reactive item signals. |
| [`Switch`][wybthon.Switch] / [`Match`][wybthon.Match] | Multi-branch conditional rendering. |
| [`Dynamic`][wybthon.Dynamic] | Render a component chosen at runtime. |

#### Idioms

```python
from wybthon import (
    For, Index, Match, Show, Switch, component, create_signal,
)
from wybthon.html import li, p, ul


@component
def Demo():
    items, _ = create_signal(["a", "b", "c"])
    is_logged_in, _ = create_signal(False)

    return ul(
        Show(
            when=is_logged_in,
            children=lambda: li("Welcome!"),
            fallback=lambda: li("Please log in"),
        ),
        For(each=items, children=lambda item, idx: li(item(), key=idx())),
    )
```

- Pass *getters* (the signal accessor itself) to `when` / `each`.
- `children` may be a `VNode`, a callable returning a `VNode`, or the
  per-item mapping callback for `For` / `Index`.

#### See also

- [Concepts → Components](../concepts/components.md)
- [Authoring patterns](../guides/authoring-patterns.md)
- [`map_array`][wybthon.map_array] / [`index_array`][wybthon.index_array]
  for reactive list mapping outside of `For` / `Index`.
