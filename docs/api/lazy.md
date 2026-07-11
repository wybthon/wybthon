### wybthon.lazy

::: wybthon.lazy

#### What's in this module

[`lazy`][wybthon.lazy] defers loading a component until the first time
it mounts. The load is backed by a [`Resource`][wybthon.Resource], so
it integrates with [`Suspense`][wybthon.Suspense] (fallback while
loading) and [`ErrorBoundary`][wybthon.ErrorBoundary] (load failures)
automatically, matching SolidJS's `lazy(() => import(...))`.

#### Quick example

```python
from wybthon import Route, Router, Suspense, component, lazy
from wybthon.html import p

HeavyChart = lazy(lambda: ("app.heavy_chart", "Chart"))

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

- The loader may return a component callable, an imported module, a
  module-path string, or a `(module_path, attr)` tuple.
- Async loaders can `await` arbitrary work first (for example
  `micropip.install(...)` in Pyodide) before returning the component.
- The resolved component is cached; the loader runs at most once.
- `HeavyChart.preload()` starts the load early (handy for hover or
  focus warm-ups) and returns the backing resource.
- A loader error raises into the nearest `ErrorBoundary`.

#### See also

- [Concepts → Suspense and Lazy Loading](../concepts/suspense-lazy.md)
- [`Suspense`][wybthon.Suspense]
- [Performance guide](../guides/performance.md)
