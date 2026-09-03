### wybthon.lazy

::: wybthon.lazy

#### What's in this module

[`lazy`][wybthon.lazy] defers loading a component until it first mounts.
The load is backed by an async [`create_memo`][wybthon.create_memo], so
it suspends into the nearest [`Loading`][wybthon.Loading] while in
flight and raises into the nearest [`Errored`][wybthon.Errored] on
failure, matching SolidJS's `lazy(() => import(...))` adapted to
Python's import system.

| Name | Description |
| --- | --- |
| [`lazy`][wybthon.lazy] | `lazy(loader)`; the loader is a zero-arg callable, sync or async, returning a component, a module, a module-path string, or a `(module_path, attr)` tuple. |
| `LazyComponent` | What `lazy` returns: a `Component` with `.preload()` to start the load early. |

```python
from wybthon import Link, Loading, Route, Router, component, lazy, p

About = lazy(lambda: ("app.about.page", "Page"))     # importlib, attribute "Page"

async def load_chart():
    import micropip
    await micropip.install("app-charts")
    import app_charts
    return app_charts.Chart

Chart = lazy(load_chart)

@component
def App():
    return Loading(
        lambda: Router([Route("/about", About), Route("/chart", Chart)]),
        fallback=lambda: p("Loading..."),
    )

nav_link = Link("Chart", href="/chart", on_mouseover=lambda e: Chart.preload())
```

- When the loader returns a module, the export is picked by convention:
  `Page`, then `default`, then the first callable.
- The loader runs at most once; the resolved component is cached across
  unmounts.
- Props and children passed to the lazy component are forwarded to the
  loaded component unchanged.

#### See also

- [Loading](loading.md) and [Error boundary](error_boundary.md)
- [Router](router.md): pair with `Route` for code-split pages
- [Concepts: Async and loading](../concepts/async-loading.md)
- [Guides: Performance](../guides/performance.md)
