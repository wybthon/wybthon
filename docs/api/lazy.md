### wybthon.lazy

::: wybthon.lazy

#### What's in this module

[`lazy`][wybthon.lazy] defers loading a component until the first time
it mounts. The load is backed by an async
[`create_memo`][wybthon.create_memo], so it integrates with
[`Loading`][wybthon.Loading] (fallback while loading) and
[`ErrorBoundary`][wybthon.ErrorBoundary] (load failures)
automatically, matching SolidJS's `lazy(() => import(...))`.

#### Quick example

```python
from wybthon import Loading, Route, Router, component, lazy
from wybthon.html import p

HeavyChart = lazy(lambda: ("app.heavy_chart", "Chart"))

routes = [
    Route(path="/charts", component=HeavyChart),
]


@component
def App():
    return Loading(
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
  focus warm-ups) and returns `None`.
- A loader error raises into the nearest `ErrorBoundary`.

#### See also

- [Concepts → Async and Loading](../concepts/async-loading.md)
- [`Loading`][wybthon.Loading]
- [Performance guide](../guides/performance.md)
