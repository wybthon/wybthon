# Getting Started

Follow these steps to install Wybthon and build your first app.

## Prerequisites

- Python 3.9+
- A modern browser

## Install

```bash
pip install wybthon
```

This installs the library and the `wyb` CLI. In Pyodide, install at runtime via `micropip`:

```python
import micropip
await micropip.install("wybthon")
```

## Start from the template

The fastest way to a running app is the [demo-template](https://github.com/wybthon/demo-template) repository: a static Wybthon app with `index.html`, a `bootstrap.js` that loads Pyodide, and an `app/` package ready to edit.

```bash
git clone https://github.com/wybthon/demo-template.git my-app
cd my-app
pip install wybthon
wyb dev --dir . --watch app --open
```

For larger reference apps, see the [demo apps guide](guides/demo-app.md).

## Dev server with auto-reload

The `wyb dev` command serves your project with hot reload:

```bash
wyb dev --dir .
```

Flags:

- `--host` (default `127.0.0.1`)
- `--port` (default `8000`, auto-increments on conflict)
- `--watch` (defaults to `src`)

The dev server exposes an SSE endpoint (`/__sse`) that your page can listen to for reload events; see the [dev server guide](guides/dev-server.md).

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

!!! tip "Why `span(count)` instead of `f'Count: {count()}'`?"
    Reading `count()` eagerly at setup captures the current value
    once. To get reactive updates, embed the *accessor* itself; the
    reconciler wraps it as a reactive hole and updates only that DOM
    node when the signal changes. See
    [Reactive Holes](concepts/primitives.md#reactive-holes).

## Next steps

- Read the [Mental model](concepts/mental-model.md) for a deeper tour.
- Browse [Authoring patterns](guides/authoring-patterns.md) for idiomatic recipes.
- Walk through the [examples](examples.md) to see complete apps.
- Coming from React or SolidJS? Try [Migrating from React](guides/migrating-from-react.md) or [Migrating from Solid](guides/migrating-from-solid.md).
