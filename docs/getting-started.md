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

## Minimal component example

Using the `@component` decorator (recommended):

```python
from wybthon import Element, component, h, h2, render

@component
def Hello(name: str = "world"):
    return h2(f"Hello, {name}!")

tree = Hello(name="Python")
container = Element("body", existing=True)
render(tree, container)
```

Stateful component with signals:

```python
from wybthon import Element, button, component, create_signal, div, h, on_mount, p, render

@component
def Counter(initial: int = 0):
    count, set_count = create_signal(initial)

    on_mount(lambda: print("Counter mounted"))

    def render_fn():
        return div(
            p(f"Count: {count()}"),
            button("Increment", on_click=lambda e: set_count(count() + 1)),
        )
    return render_fn

tree = h(Counter, {"initial": 5})
container = Element("body", existing=True)
render(tree, container)
```

Traditional function component (also supported):

```python
from wybthon import Element, h, h2, render

def Hello(props):
    name = props.get("name", "world")
    return h2(f"Hello, {name}!")

tree = h(Hello, {"name": "Python"})
container = Element("body", existing=True)
render(tree, container)
```

See: [Authoring Patterns](guides/authoring-patterns.md)
