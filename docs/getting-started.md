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

Using the `@component` decorator:

```python
from wybthon import Element, component, h2, render

@component
def Hello(name="world"):
    # ``name`` is a reactive accessor; passing it as a child creates a
    # reactive hole, so the text node updates whenever the parent
    # passes a new ``name``.
    return h2("Hello, ", name, "!")

tree = Hello(name="Python")
container = Element("body", existing=True)
render(tree, container)
```

Stateful component with signals:

```python
from wybthon import (
    Element, button, component, create_signal, div, h, on_mount, p, render, span, untrack,
)

@component
def Counter(initial=0):
    # ``initial`` is a reactive accessor; ``untrack`` reads its
    # current value without subscribing -- perfect as a signal seed.
    count, set_count = create_signal(untrack(initial))

    on_mount(lambda: print("Counter mounted"))

    # Component body runs ONCE.  ``count`` is a *reactive hole*:
    # only the highlighted text node updates when the signal changes.
    return div(
        p("Count: ", span(count)),
        button("Increment", on_click=lambda e: set_count(count() + 1)),
    )

tree = h(Counter, {"initial": 5})
container = Element("body", existing=True)
render(tree, container)
```

> **Why `span(count)` instead of `f"Count: {count()}"`?**  Reading
> `count()` eagerly at setup captures the current value once.  To get
> reactive updates, embed the *accessor* — the reconciler wraps it as
> a reactive hole and updates only that DOM node when the signal
> changes.  See [Reactive Holes](concepts/primitives.md#reactive-holes).

See: [Authoring Patterns](guides/authoring-patterns.md)
