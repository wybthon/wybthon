# Getting started

Wybthon runs client-side Python through Pyodide. Components run once and return HTML written as template strings; the accessors and expressions you interpolate update their own parts of the page. The renderer batches every DOM mutation into one call to a small JavaScript kernel.

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
from wybthon import component, create_signal, html


@component
def App():
    count, set_count = create_signal(0)

    def increment():
        set_count(lambda n: n + 1)

    return html(t"""
      <div>
        <h1>My Wybthon app</h1>
        <button onclick={increment}>Count: {count}</button>
      </div>
    """)


def app():
    return App()
```

[`html`][wybthon.html] takes a `t"..."` template string (new in Python 3.14) and returns a node. The markup is ordinary HTML, and each `{...}` is a Python expression placed where it appears. Wybthon compiles each template literal once, so mounting it again later only fills in the values.

`count` is an accessor. Interpolating it creates a reactive binding, so the button's text updates whenever `count` changes; reading `count()` directly during setup would capture a one-time value. `onclick={increment}` binds a delegated click handler. The handler takes no arguments because it doesn't need the event, and writes made in a handler batch automatically.

`increment` is a named function rather than an inline `lambda`, because Python doesn't allow a bare `lambda` inside a template interpolation. If you want one inline, wrap it in parentheses: `{(lambda: set_count(0))}`. See [Templates](concepts/templates.md) for the full syntax.

`app` is the entry point named in `wybthon.toml`. It returns the root view, and the bootstrap mounts it into `#app`. The generated project prerenders `/` at build time, so the page shows the counter before Pyodide has loaded and then [hydrates](concepts/server-rendering.md) it. Outside the production bootstrap, mount a view yourself with [`render`][wybthon.render].

## Add props

A component that takes inputs declares them on a [`Props`][wybthon.Props] class. Each [`Prop[T]`][wybthon.Prop] field reads as an accessor, and pyright and mypy check every call without a plugin:

```python
from wybthon import Prop, Props, component, create_signal, html, prop


class CounterProps(Props):
    label: Prop[str]
    initial: Prop[int] = prop(default=0)


@component
def Counter(props: CounterProps):
    count, set_count = create_signal(props.initial.peek())

    def increment():
        set_count(lambda n: n + 1)

    return html(t"""
      <div>
        <p>{props.label}: {count}</p>
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

Calling `Counter(...)` inside an interpolation keeps full type checking of its props. Templates also accept a tag form, `<{Counter} label="Clicks" initial={5} />`, which reads like the surrounding markup and is checked at run time in dev mode. See [Components](concepts/components.md) for children, callbacks, and defaults.

## Test it

[`wybthon.testing`](api/testing.md) renders components into an in-memory DOM in plain CPython:

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

The output in `dist/` contains prerendered pages, hashed source archives, and a browser bootstrap. Each page carries the asset manifest inline and preloads Pyodide and the archives, so the browser starts fetching them while it parses the HTML. Production builds turn dev mode off before your application imports, so dev-only checks and warnings don't ship. Deploy those files to a static host. See [Deployment](guides/deployment.md) for base paths, pinned dependencies, lazy chunks, and route fallback configuration.

Continue with the [mental model](concepts/mental-model.md), [templates](concepts/templates.md), [stores](concepts/stores.md), and [runtime contracts](concepts/runtime-contracts.md).
