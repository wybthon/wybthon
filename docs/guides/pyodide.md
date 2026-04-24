# Pyodide

Wybthon runs in the browser through [Pyodide](https://pyodide.org/), a CPython distribution compiled to WebAssembly. Most of the framework is plain Python; Pyodide-specific concerns surface only at the boundaries — module loading, async/event-loop integration, and JS interop.

## The basics

- Use [`micropip`](https://micropip.pyodide.org/) to install Python packages from PyPI at runtime.
- Import from `wybthon` after the library files exist in the Pyodide filesystem (the demo's `bootstrap.js` does this for you).
- Bridge to the browser using the [`js` module](https://pyodide.org/en/stable/usage/api/python-api/ffi.html#module-js) and [`pyodide.ffi`](https://pyodide.org/en/stable/usage/api/python-api/ffi.html).

```python
import micropip
await micropip.install("wybthon")
import wybthon
```

## The Pyodide event loop

Pyodide ships with a single-threaded event loop integrated with the browser's microtask queue. A few practical implications:

- **There are no native threads in WebAssembly.** Anything that blocks the main thread will freeze the page. Prefer async APIs (`asyncio.sleep`, `await fetch(...)`) over busy loops.
- **Use `asyncio` for cooperative concurrency.** `asyncio.create_task`, `asyncio.gather`, and `asyncio.sleep` all work as you'd expect.
- **`await` JavaScript promises directly.** Pyodide adapts Python coroutines to JS Promises and vice versa. From Python you can `await fetch(...)`; from JavaScript you can `await pyodide.runPythonAsync(...)`.
- **Long computations should yield.** Wybthon uses [`batch`][wybthon.batch] to coalesce reactive updates, but if you have a slow, synchronous routine, break it up with `await asyncio.sleep(0)` or move it to a Pyodide [web worker](https://pyodide.org/en/stable/usage/webworker.html) (advanced; outside the scope of this guide).

```python
import asyncio

from js import fetch
from wybthon import create_resource


async def fetch_user(uid: str) -> dict:
    response = await fetch(f"/api/users/{uid}")
    if not response.ok:
        raise RuntimeError(f"HTTP {response.status}")
    return (await response.json()).to_py()


user = create_resource(lambda: ("u-1",), fetch_user)
```

[`create_resource`][wybthon.create_resource] integrates with the event loop automatically: it awaits your fetcher, exposes `loading` / `error` / `latest` signals, and works seamlessly with [`Suspense`][wybthon.Suspense] for declarative loading UIs.

## JavaScript interop tips

- Convert Python collections to JS objects with `pyodide.ffi.to_js(...)` when calling JS APIs that expect plain objects (e.g. `JSON.stringify` or `fetch` request bodies).
- Convert JS objects to Python with `.to_py()` (most JS values returned by `await` calls have this method).
- Wrap Python callbacks in `create_proxy` when handing them to JS APIs that store them long term — Wybthon already does this internally for event handlers and `popstate` listeners, but you'll need to do it manually for direct `addEventListener` calls.

## Lazy imports and module loading

[`lazy()`][wybthon.lazy] and [`load_component()`][wybthon.load_component] use Python's regular import system, so the only requirement is that the target module is reachable on `sys.path` at import time:

- Ensure module files exist in the Pyodide filesystem before calling `importlib.import_module`. The demo's `bootstrap.js` copies `examples/demo/app/**` into `/app`, so imports like `"app.about.page"` resolve.
- For third-party packages, install them with `micropip` before attempting a lazy import.
- Python imports are synchronous, but fetching files into the Pyodide filesystem is asynchronous on the JS side. Copy or preload modules before invoking lazy loaders, or call [`preload_component()`][wybthon.preload_component] on user intent (e.g. link hover) to warm the import cache.
- Attribute resolution defaults to `Page` or `default` when unspecified; otherwise pass the export name explicitly.

```python
from wybthon import lazy, preload_component


def AboutLazy():
    return ("app.about.page", "Page")


About = lazy(AboutLazy)


def on_hover_about(_evt):
    preload_component("app.about.page", "Page")
```

## Next steps

- Browse the [dev server guide](dev-server.md) for hot-reload tips.
- Read [Suspense and lazy loading](../concepts/suspense-lazy.md) for end-to-end async UI patterns.
