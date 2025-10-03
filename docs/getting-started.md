# Getting Started

Follow these steps to run the demo and start hacking on Wybthon.

## Prerequisites

- Python 3.9+
- A modern browser

## Run the demo (no install)

```bash
python -m http.server
# Then open http://localhost:8000/examples/demo/index.html
```

The demo loads Pyodide, mounts the library from `src/wybthon/`, then runs the app under `examples/demo/app/`.

## Dev server with auto-reload

Install the package locally (for the `wyb` CLI), then start the dev server:

```bash
pip install .
wyb dev --dir .
```

Flags:

- `--host` (default `127.0.0.1`)
- `--port` (default `8000`, auto-increments on conflict)
- `--watch` (defaults to `src` and `examples`)

The dev server exposes an SSE endpoint (`/__sse`) that the demo listens to for reload events.

## Install from PyPI (experimental)

```bash
pip install wybthon
```

In Pyodide via `micropip`:

```python
import micropip
await micropip.install("wybthon")
```

> TODO: Provide a minimal component example here once the authoring flow is finalized (function vs class components, recommended structure).

## Minimal component example

Function component:

```python
from wybthon import h, render, Element

def Hello(props):
    name = props.get("name", "world")
    return h("h2", {}, f"Hello, {name}!")

tree = h(Hello, {"name": "Python"})
container = Element("body", existing=True)
render(tree, container)
```

Class component with state:

```python
from wybthon import Component, h, signal, render, Element

class Counter(Component):
    def __init__(self, props):
        super().__init__(props)
        self.count = signal(0)

    def render(self):
        return h(
            "div",
            {},
            h("p", {}, f"Count: {self.count.get()}"),
            h("button", {"on_click": lambda e: self.count.set(self.count.get() + 1)}, "Increment"),
        )

tree = h(Counter, {})
container = Element("body", existing=True)
render(tree, container)
```

See: [Authoring Patterns](guides/authoring-patterns.md)
