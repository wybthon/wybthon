### Pyodide

Wybthon runs in the browser via Pyodide.

Key points:

- Use `micropip` to install packages when needed
- Import from `wybthon` after loading the library files into Pyodide FS (the demo does this for you)
- Interop with JS via `js` and `pyodide.ffi`

```python
import micropip
await micropip.install("wybthon")
import wybthon
```

> TODO: Add guidance on threading/event loops and async APIs in Pyodide.

#### Lazy imports and module loading caveats

When using `lazy()` or `load_component()` in Pyodide:

- Ensure the module files exist in the Pyodide filesystem before calling `importlib.import_module`. The demo's `bootstrap.js` copies `examples/demo/app/**` into `/app`, so imports like `"app.about.page"` resolve.
- If loading third-party packages, install them with `micropip` before attempting lazy import.
- Python imports are synchronous, but fetching files into the FS is asynchronous in JS. Copy or preload files before invoking lazy loaders, or use `preload_component()` on user intent (e.g., link hover) to warm the import cache.
- Attribute resolution defaults to `Page` or `default` if unspecified; otherwise pass the export name explicitly.

Example:

```python
from wybthon import lazy, preload_component

def AboutLazy():
    return ("app.about.page", "Page")

About = lazy(AboutLazy)

def on_hover_about(_evt):
    preload_component("app.about.page", "Page")
```
