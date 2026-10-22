# Getting started

Wybthon runs client-side Python through Pyodide. Components run once and return HTML written as template strings, and a compiler makes each dynamic expression in that markup update its own part of the page, as Solid's does for JSX. The renderer batches every DOM mutation into one call to a small JavaScript kernel.

## Create an application

Install Python 3.14 or later and Wybthon:

```bash
python -m pip install wybthon
wyb init my-app
cd my-app
wyb dev --open
```

The generated project has `app/main.py`, `index.html`, `pyproject.toml`, and `wybthon.toml`. The development server builds the app in dev mode and reloads the browser after source, configuration, or public asset changes. Pyodide requires a network connection on the first load unless you host the runtime locally.

## Write a component

`wyb init` generates this `app/main.py`:

```python
"""A run-once component with a reactive counter."""

from wybthon import component, create_signal, html


@component
def App():
    count, set_count = create_signal(0)

    def increment():
        set_count(lambda n: n + 1)

    return html(t"""
      <div>
        <h1>My Wybthon app</h1>
        <button onclick={increment}>Count: {count()}</button>
        <p>Doubled: {count() * 2}</p>
      </div>
    """)


def app():
    """Return the root view; the bootstrap renders (or hydrates) it into the mount element."""
    return App()
```

[`html`][wybthon.html] takes a `t"..."` template string (new in Python 3.14) and returns a node. The markup is ordinary HTML, and each `{...}` is a Python expression placed where it appears.

`App` runs once. `{count()}` and `{count() * 2}` are *dynamic* expressions: they call something, so Wybthon's [compiler](concepts/compiler.md) turns each one into a getter before the module runs, the way Solid's compiler treats an expression in JSX. When `count` changes, those two text nodes update and nothing else runs. An expression that's just a name or a constant, such as `{title}`, is placed once. `onclick={increment}` binds a delegated click handler; event handlers are never wrapped. The handler takes no arguments because it doesn't need the event, and writes made in a handler batch automatically.

The compiler runs wherever your code does: in `wyb dev` and `wyb build`, in modules imported after `wybthon`, under pytest, and for scripts run with `wyb run script.py`. You don't call it yourself.

`increment` is a named function rather than an inline `lambda`, because Python doesn't allow a bare `lambda` inside a template interpolation. If you want one inline, wrap it in parentheses: `onclick={(lambda: set_count(0))}`. See [Templates](concepts/templates.md) for the full syntax.

`app` is the entry point named in `wybthon.toml`. It returns the root view, and the bootstrap mounts it into `#app`. The generated project prerenders `/` at build time, so the page shows the counter before Pyodide has loaded and then [hydrates](concepts/server-rendering.md) it. Outside the production bootstrap, mount a view yourself with [`render`][wybthon.render].

## Add props

A component that takes inputs declares them on a [`Props`][wybthon.Props] class. Fields are plain annotations, and pyright and mypy check every call without a plugin:

```python
from wybthon import Props, component, create_signal, html, untrack


class CounterProps(Props):
    label: str
    initial: int = 0


@component
def Counter(props: CounterProps):
    count, set_count = create_signal(untrack(lambda: props.initial))

    def increment():
        set_count(lambda n: n + 1)

    return html(t"""
      <div>
        <p>{props.label}: {count()}</p>
        <button onclick={increment}>+1</button>
      </div>
    """)


@component
def App():
    return html(t"""
      <main>
        <h1>My Wybthon app</h1>
        {Counter(label="Clicks", initial=5)}
      </main>
    """)
```

Reading `props.label` returns the parent's value, tracked, as in Solid. In the template, `{props.label}` is dynamic, so it updates if the parent passes an expression that changes. `initial` only seeds the signal, so it's read once with [`untrack`][wybthon.untrack]; reading a prop at the top level of the body without it would warn in dev mode, because that read never updates.

Calling `Counter(...)` inside an interpolation keeps full type checking of its props. Templates also accept a tag form, `<{Counter} label="Clicks" initial={5} />`, which reads like the surrounding markup and is checked at run time in dev mode. See [Components](concepts/components.md) for children, callbacks, and defaults.

## Test it

[`wybthon.testing`](api/testing.md) renders components into an in-memory DOM in plain CPython. Wybthon's pytest plugin compiles the templates in test modules, so they behave exactly as they do in the app:

```python
from wybthon.testing import fire, render


def test_counter():
    screen = render(Counter(label="Clicks"))
    fire.click(screen.get_by_text("+1"))
    assert screen.get_by_text("Clicks: 1")
```

## Build and preview

```bash
wyb build
wyb preview
```

The output in `dist/` contains prerendered pages, hashed source archives with every template compiled ahead of time, and a browser bootstrap. Each page carries the asset manifest inline and preloads Pyodide and the archives, so the browser starts fetching them while it parses the HTML. Production builds turn dev mode off before your application imports, so dev-only checks and warnings don't ship. Deploy those files to a static host. See [Deployment](guides/deployment.md) for base paths, pinned dependencies, lazy chunks, and route fallback configuration.

Continue with the [mental model](concepts/mental-model.md), [templates](concepts/templates.md), [the compiler](concepts/compiler.md), [stores](concepts/stores.md), and [runtime contracts](concepts/runtime-contracts.md).
