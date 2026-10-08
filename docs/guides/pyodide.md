# Pyodide

Wybthon runs in the browser through [Pyodide](https://pyodide.org/), a CPython distribution compiled to WebAssembly. Most of the framework is plain Python; Pyodide-specific concerns surface only at the boundaries: module loading, async and event-loop integration, and JS interop.

## The basics

- Wybthon requires Python 3.14, so in the browser it needs Pyodide 314 or newer. `wyb init` pins Pyodide 314.0.6, the version the framework's own browser test suite runs on.
- `wyb build` packages Wybthon and your application into archives that its generated bootstrap loads, so a project doesn't install Wybthon at runtime. See [Deployment](deployment.md).
- Use [`micropip`](https://micropip.pyodide.org/) to install other Python packages from PyPI at runtime, or list them under `packages` and `wheels` in `wybthon.toml`.
- Bridge to the browser with the [`js` module](https://pyodide.org/en/stable/usage/api/python-api/ffi.html#module-js) and [`pyodide.ffi`](https://pyodide.org/en/stable/usage/api/python-api/ffi.html). Wybthon doesn't re-export `js`; import it yourself where you need it.

A project's entry function returns the root view, and the generated bootstrap renders it into the mount element (or hydrates it when the page was prerendered):

```python
from wybthon import button, component, create_signal, div, h1


@component
def App():
    count, set_count = create_signal(0)
    return div(
        h1("My Wybthon app"),
        button(t"Count: {count}", on_click=lambda: set_count(lambda n: n + 1)),
    )


def app():
    return App()
```

Outside a project (in a Pyodide console, say), install Wybthon with `micropip` and render yourself:

```python
import micropip

await micropip.install("wybthon")

from wybthon import render

render(App(), "#app")
```

## The Pyodide event loop

Pyodide ships with a single-threaded event loop integrated with the browser's microtask queue. A few practical implications:

- **There are no native threads in WebAssembly.** Anything that blocks the main thread freezes the page. Prefer async APIs (`asyncio.sleep`, `await fetch(...)`) over busy loops.
- **Use `asyncio` for cooperative concurrency.** `asyncio.create_task`, `asyncio.gather`, and `asyncio.sleep` work as you'd expect.
- **`await` JavaScript promises directly.** Pyodide adapts Python coroutines to JS Promises and vice versa. From Python you can `await fetch(...)`; from JavaScript you can `await pyodide.runPythonAsync(...)`.
- **Wybthon flushes on microtasks.** Signal writes are staged and applied on the next microtask (`queueMicrotask`) and at the end of every event handler. You never call [`flush`][wybthon.flush] in browser code; it exists for tests and scripts without an event loop.
- **Long computations should yield.** If you have a slow synchronous routine, break it up with `await asyncio.sleep(0)` inside an async memo or action, or move it to a Pyodide [web worker](https://pyodide.org/en/stable/usage/webworker.html) (advanced; outside the scope of this guide).

```python
from js import fetch

from wybthon import create_memo


async def fetch_user() -> dict:
    response = await fetch("/api/users/u-1")
    if not response.ok:
        raise RuntimeError(f"HTTP {response.status}")
    return (await response.json()).to_py()


user = create_memo(fetch_user)
```

Async memos and [`action`][wybthon.action]s integrate with Pyodide's event loop automatically: `await` inside them runs on the same loop as the browser's microtask queue, so awaiting `fetch(...)` or any JS promise just works. [`create_memo`][wybthon.create_memo] with an `async def` body raises [`NotReadyError`][wybthon.NotReadyError] on reads before the first value (which [`Loading`][wybthon.Loading] boundaries catch to show fallbacks) and runs later recomputes as transitions that hold the dependent UI until the new value lands. Use [`is_pending`][wybthon.is_pending] and [`latest`][wybthon.latest] to observe in-flight state, [`resolve`][wybthon.resolve] to await the next settled value, and [`refresh`][wybthon.refresh] to recompute quietly.

## JavaScript interop tips

- Convert Python collections to JS objects with `pyodide.ffi.to_js(...)` when calling JS APIs that expect plain objects (for example `JSON.stringify` or `fetch` request bodies).
- Convert JS objects to Python with `.to_py()`; most JS values returned by `await` calls have this method.
- Wrap Python callbacks in `create_proxy` when handing them to JS APIs that keep them (`setInterval`, `addEventListener`). Wybthon already does this internally for its delegated event handlers and its `popstate` listener. Destroy the proxy in a cleanup:

```python
from wybthon import component, create_signal, div, on_settled


@component
def Clock():
    now, set_now = create_signal("")

    def start():
        from js import Date, clearInterval, setInterval
        from pyodide.ffi import create_proxy

        proxy = create_proxy(lambda: set_now(Date().toLocaleTimeString()))
        handle = setInterval(proxy, 1000)
        return lambda: (clearInterval(handle), proxy.destroy())

    on_settled(start)
    return div(now)
```

- For imperative DOM work, [`Ref`][wybthon.Ref] gives you an [`Element`][wybthon.Element] whose `.element` is the raw node. Event handlers receive a [`DomEvent`][wybthon.DomEvent] built from a payload (no bridge crossing to read `e.target.value`); `e.raw` is the native event when you need it.

## Lazy imports and module loading

[`lazy`][wybthon.lazy] uses Python's regular import system, so the only requirement is that the target module is reachable on `sys.path` at import time:

- In a `wyb build` project, the application archive is unpacked before your entry runs, so imports like `"app.about.page"` resolve. Modules in an explicit `[chunks]` group are fetched the first time a lazy component in that chunk renders; see [Deployment](deployment.md#explicit-lazy-chunks).
- For third-party packages, use an async loader that `await`s `micropip.install(...)` before importing.
- Python imports are synchronous, but fetching files into the Pyodide filesystem is asynchronous on the JS side. Copy or preload modules before invoking lazy loaders, or call the lazy component's `.preload()` method on user intent (link hover) to warm the import.
- Attribute resolution defaults to `Page`, then `default`, then the first callable export; otherwise pass the export name explicitly.

```python
from wybthon import lazy
from wybthon.router import Link

About = lazy(lambda: ("app.about.page", "Page"))


async def load_charts():
    import micropip

    await micropip.install("app-charts")
    import app_charts

    return app_charts.Chart


Chart = lazy(load_charts)

Link("About", href="/about", on_mouseenter=lambda: About.preload())
```

## Dev mode

Pyodide takes over a second to load and initialize. [Server rendering](../concepts/server-rendering.md) shows prerendered HTML during that time, and the page hydrates once Python is ready.

Wybthon's dev-mode diagnostics (prop validation, write-in-scope errors, and warnings) are on by default, and `wyb dev` keeps them on. Production builds from `wyb build` call [`set_dev_mode(False)`][wybthon.set_dev_mode] before the application imports, so you don't need to. Outside a project build, call it yourself at startup. [`is_dev_mode()`][wybthon.is_dev_mode] reads the current mode.

## Next steps

- Browse the [dev server guide](dev-server.md) for hot-reload tips.
- Read [Async and Loading](../concepts/async-loading.md) for end-to-end async UI patterns.
- See the [Deployment guide](deployment.md) for hosting a Pyodide app.
