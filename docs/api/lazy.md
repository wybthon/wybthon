### wybthon.lazy

::: wybthon.lazy

#### What's in this module

[`lazy`][wybthon.lazy] defers loading a component until it first mounts, and
[`lazy_module`][wybthon.lazy_module] defers any other import until it's first needed.
A lazy component's load is backed by an async [`create_memo`][wybthon.create_memo], so
it suspends into the nearest [`Loading`][wybthon.Loading] while in
flight and raises into the nearest [`Errored`][wybthon.Errored] on
failure, matching SolidJS's `lazy(() => import(...))` adapted to
Python's import system.

| Name | Description |
| --- | --- |
| [`lazy`][wybthon.lazy] | `lazy(loader, *, chunk=None)`; the loader is a zero-arg callable, sync or async, returning a component, a module, a module-path string, or a `(module_path, attr)` tuple. `chunk` names a build chunk to fetch first. |
| [`LazyComponent`][wybthon.lazy.LazyComponent] | What `lazy` returns: a `Component` with `.preload()` to start the load early and `.retry()` to retry a failed load. |
| [`lazy_module`][wybthon.lazy_module] | `lazy_module(loader, *, chunk=None)`: a cached, on-demand import of a module that isn't a component, the counterpart of Solid 2.0's `lazyModule`. |
| [`LazyModule`][wybthon.LazyModule] | What `lazy_module` returns: call it (or `.preload()`) for an awaitable of the module; `.peek()` returns the module once it has loaded, else `None`. |

```python
from wybthon import Loading, component, html, lazy
from wybthon.router import Link, Route, Router

About = lazy(lambda: ("app.about.page", "Page"))  # importlib, attribute "Page"


async def load_chart():
    import micropip

    await micropip.install("app-charts")
    import app_charts

    return app_charts.Chart


Chart = lazy(load_chart)


@component
def App():
    return Loading(
        Router([Route("/about", About), Route("/chart", Chart)]),
        fallback=html(t"<p>Loading...</p>"),
    )


nav_link = Link("Chart", href="/chart", on_mouseover=Chart.preload)
```

- When the loader returns a module, the export is picked by convention:
  `Page`, then `default`, then the first callable.
- The loader runs at most once; the resolved component is cached across
  unmounts.
- Props and children passed to the lazy component are forwarded to the
  loaded component unchanged.

`lazy_module` loads code that isn't a component: a route table, a
parser, a charting library's helpers. The loader runs once, on the first
call or `.preload()`, and every caller awaits the same import.

```python
from wybthon import lazy_module

admin = lazy_module(lambda: "app.admin.routes", chunk="admin")


async def open_admin():
    routes = await admin()  # imports on first use, then cached
    routes.register()


admin.peek()  # the module, or None until it has loaded
```

#### See also

- [Loading](loading.md) and [Error boundary](error_boundary.md)
- [Router](router.md): pair with `Route` for code-split pages
- [Concepts: Async and loading](../concepts/async-loading.md)
- [Guides: Performance](../guides/performance.md)
