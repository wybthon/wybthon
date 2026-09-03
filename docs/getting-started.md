# Getting started

Follow these steps to install Wybthon, boot it in a browser page, and write your first components.

## Prerequisites

- Python 3.12 or newer (for the `wyb` CLI and for running unit tests in CPython).
- A modern browser. In the browser, Wybthon runs on Pyodide 0.27 or newer (Python 3.12); the examples below pin Pyodide 314.0.6 (Python 3.14).

## Install

```bash
pip install wybthon
```

This installs the library and the `wyb` CLI. Inside Pyodide, install at runtime with `micropip`:

```python
import micropip
await micropip.install("wybthon")
```

## Start from the template

The fastest way to a running app is the [demo-template](https://github.com/wybthon/demo-template) repository: a static Wybthon app with an `index.html`, a `bootstrap.js` that loads Pyodide, and an `app/` package ready to edit.

```bash
git clone https://github.com/wybthon/demo-template.git my-app
cd my-app
pip install wybthon
wyb dev --dir . --watch app --open
```

For larger reference apps, see the [demo apps guide](guides/demo-app.md).

## A page skeleton from scratch

If you'd rather see every moving part, three files are enough. First, an `index.html` with a mount point and a module script:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>My Wybthon app</title>
  </head>
  <body>
    <div id="app"></div>
    <script type="module">
      import(`./bootstrap.js?v=${Date.now()}`);
    </script>
  </body>
</html>
```

Second, a `bootstrap.js` that loads Pyodide, installs Wybthon from PyPI, and runs your entry module:

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

const source = await (await fetch(`./main.py?v=${Date.now()}`)).text();
await pyodide.runPythonAsync(source);
```

Third, `main.py`, the Python entry point that renders your root component into `#app`:

```python
from wybthon import button, component, create_signal, div, p, render


@component
def Counter():
    count, set_count = create_signal(0)
    return div(
        p("Count: ", count),
        button("Increment", on_click=lambda e: set_count(lambda n: n + 1)),
    )


render(Counter(), "#app")
```

Serve the folder with `wyb dev --dir . --watch . --open` and you have a working app.

## Dev server with auto-reload

The `wyb dev` command serves a directory and reloads the page whenever a watched file changes:

```bash
wyb dev --dir .
```

Flags:

- `--dir`: root directory to serve. The default points at the Wybthon checkout, so pass `--dir .` for your own project.
- `--host` (default `127.0.0.1`) and `--port` (default `8000`; the next free port is used on conflict).
- `--watch`: directories to watch for changes (defaults to `src`; pass it with no values to disable reloads).
- `--mount /prefix=path`: serve an extra directory under a URL prefix (repeatable).
- `--open` and `--open-path`: open the browser after startup, optionally to a specific path.

The server exposes an SSE endpoint (`/__sse`) that the page listens to for reload events. See the [dev server guide](guides/dev-server.md) for details.

## Your first component

A component is a function decorated with [`component`][wybthon.component]. Every parameter becomes a [`Prop[T]`][wybthon.Prop] accessor, and [`prop`][wybthon.prop] declares a typed default:

```python
from wybthon import Prop, component, h2, prop, render


@component
def Hello(name: Prop[str] = prop("world")):
    # ``name`` is an accessor. Placing it in the tree creates a reactive
    # hole, so the text updates whenever the parent passes a new value.
    return h2("Hello, ", name, "!")


render(Hello(name="Python"), "#app")
```

Calling a component with keyword arguments returns a VNode, so trees compose the same way elements do. Positional arguments become the `children` prop.

### Adding state

```python
from wybthon import Prop, button, component, create_signal, div, on_settled, p, prop, render, span


@component
def Counter(initial: Prop[int] = prop(0)):
    # ``initial.peek()`` reads the value once, without subscribing,
    # which is exactly what a signal seed needs.
    count, set_count = create_signal(initial.peek())

    on_settled(lambda: print("Counter mounted with", count.peek()))

    # The body runs ONCE. ``count`` and the lambda are reactive holes:
    # only those two text nodes update when the signal changes.
    return div(
        p("Count: ", span(count)),
        p(lambda: "even" if count() % 2 == 0 else "odd"),
        button("Increment", on_click=lambda e: set_count(lambda n: n + 1)),
    )


render(Counter(initial=5), "#app")
```

A few things to notice:

- `create_signal` returns an accessor and a setter. Call the accessor to read (tracked) and the setter to write. Writes are **staged**: `count()` returns the old value until the next flush, which happens automatically after the event handler finishes. Use the functional form `set_count(lambda n: n + 1)` when the new value depends on the current one.
- Any zero-argument callable placed in the tree is a hole. `lambda: "even" if count() % 2 == 0 else "odd"` re-runs when `count` changes and patches only its text node.
- [`on_settled`][wybthon.on_settled] runs once after the flush that mounted the component, when the DOM is live. It may return a cleanup callable.

!!! tip "Why `span(count)` instead of `f'Count: {count()}'`?"
    Reading `count()` at the top level of the component body captures the value once, and in dev mode Wybthon warns about it because that read isn't tracked. To get updates, place the accessor itself (or a lambda that reads it) in the tree; the reconciler wraps it as a reactive hole. When a one-time read is what you want, say so with `count.peek()`.

### Passing props

Parents may pass plain values or accessors; the child code doesn't change:

```python
from wybthon import Prop, button, component, create_signal, div, p, prop


@component
def Badge(count: Prop[int] = prop(0)):
    return p("count: ", count)


@component
def Parent():
    n, set_n = create_signal(0)
    return div(
        Badge(count=7),  # static value
        Badge(count=n),  # accessor; the badge updates when n changes
        button("+", on_click=lambda e: set_n(lambda v: v + 1)),
    )
```

## Next steps

- Read the [Mental model](concepts/mental-model.md) for a deeper tour.
- Browse [Authoring patterns](guides/authoring-patterns.md) for idiomatic recipes.
- Walk through the [examples](examples.md) to see complete modules.
- Coming from React or SolidJS? Try [Migrating from React](guides/migrating-from-react.md) or [Migrating from Solid](guides/migrating-from-solid.md).
