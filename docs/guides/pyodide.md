# Pyodide

Wybthon runs in the browser through [Pyodide](https://pyodide.org/), a CPython distribution compiled to WebAssembly. Most of the framework is plain Python; Pyodide-specific concerns surface only at the boundaries: module loading, async and event-loop integration, and JS interop.

## The basics

- Wybthon requires Pyodide 0.27 or newer (Python 3.12). The framework's own browser test suite runs on Pyodide 314.0.6 (Python 3.14).
- Use [`micropip`](https://micropip.pyodide.org/) to install Python packages from PyPI at runtime.
- Import from `wybthon` after the library exists in the Pyodide filesystem; installing via `micropip` (as in the [demo-template](https://github.com/wybthon/demo-template)) handles this for you.
- Bridge to the browser with the [`js` module](https://pyodide.org/en/stable/usage/api/python-api/ffi.html#module-js) and [`pyodide.ffi`](https://pyodide.org/en/stable/usage/api/python-api/ffi.html). Wybthon doesn't re-export `js`; import it yourself where you need it.

```python
import micropip

await micropip.install("wybthon")

from wybthon import render

render(App(), "#app")
```

A minimal `bootstrap.js` that does the same from the JavaScript side:

```js
const PYODIDE_VERSION = "314.0.6";
const BASE = `https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSION}/full/`;

const { loadPyodide } = await import(`${BASE}pyodide.mjs`);
const pyodide = await loadPyodide({ indexURL: BASE });
await pyodide.loadPackage("micropip");
await pyodide.runPythonAsync(`
import micropip
await micropip.install("wybthon")
`);
await pyodide.runPythonAsync(await (await fetch("./main.py")).text());
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

- Ensure module files exist in the Pyodide filesystem before the loader runs. The demo apps' `bootstrap.js` copies the app package into `/app` (the dev server's `/__manifest` endpoint lists the files), so imports like `"app.about.page"` resolve.
- For third-party packages, use an async loader that `await`s `micropip.install(...)` before importing.
- Python imports are synchronous, but fetching files into the Pyodide filesystem is asynchronous on the JS side. Copy or preload modules before invoking lazy loaders, or call the lazy component's `.preload()` method on user intent (link hover) to warm the import.
- Attribute resolution defaults to `Page`, then `default`, then the first callable export; otherwise pass the export name explicitly.

```python
from wybthon import Link, lazy

About = lazy(lambda: ("app.about.page", "Page"))


async def load_charts():
    import micropip

    await micropip.install("app-charts")
    import app_charts

    return app_charts.Chart


Chart = lazy(load_charts)

Link("About", href="/about", on_mouseenter=lambda e: About.preload())
```

## Dev mode

Wybthon's dev-mode diagnostics are on by default. Call [`set_dev_mode(False)`][wybthon.set_dev_mode] at startup in production builds to silence warnings and skip the write-in-scope checks.

## Next steps

- Browse the [dev server guide](dev-server.md) for hot-reload tips.
- Read [Async and Loading](../concepts/async-loading.md) for end-to-end async UI patterns.
- See the [Deployment guide](deployment.md) for hosting a Pyodide app.
