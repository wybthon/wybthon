### wybthon.lazy

::: wybthon.lazy

#### What's in this module

`lazy` defers loading a component module until the first time it
mounts. Pair it with [`Suspense`][wybthon.Suspense] so users see a
fallback while the chunk arrives.

| Helper | Purpose |
| --- | --- |
| [`lazy`][wybthon.lazy] | Wrap an async loader and return a placeholder component. |
| [`load_component`][wybthon.load_component] | Manually load a component module (advanced). |
| [`preload_component`][wybthon.preload_component] | Warm the cache before a route is visited. |

#### Quick example

```python
from wybthon import Route, Router, Suspense, lazy
from wybthon.html import p


HeavyChart = lazy(load=lambda: import_module_async("app.heavy_chart"))


routes = [
    Route(path="/charts", component=HeavyChart),
]


@component
def App():
    return Suspense(
        fallback=lambda: p("Loading…"),
        children=lambda: Router(routes=routes),
    )
```

- `load` returns a coroutine that resolves to the component (or to a
  module from which an attribute is read, depending on the helper used).
- `lazy` caches the resolved component automatically.
- `preload_component(loader)` is handy for hover/focus warm-ups.

#### See also

- [Concepts → Suspense and Lazy Loading](../concepts/suspense-lazy.md)
- [`Suspense`][wybthon.Suspense]
- [Performance guide](../guides/performance.md)
