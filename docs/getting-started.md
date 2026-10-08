# Getting started

Wybthon runs client-side Python through Pyodide. Components run once; accessors and explicit expressions update their reactive parts. The renderer batches a Virtual DOM's mutations into JavaScript.

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

```python
from wybthon import button, component, create_signal, div, h1


@component
def App():
    count, set_count = create_signal(0)
    return div(
        h1("My Wybthon app"),
        button(t"Count: {count}", on_click=lambda: set_count(lambda n: n + 1)),
    )


def app():
    return App()
```

`count` is an accessor. The template string `t"Count: {count}"` (a Python 3.14 t-string) is a tracked expression, so the button's text updates whenever `count` changes; reading `count()` directly during setup would capture a one-time value. The handler takes no arguments because it doesn't need the event. Event writes batch automatically.

`app` is the entry point named in `wybthon.toml`. It returns the root view, and the bootstrap mounts it into `#app`. The generated project prerenders `/` at build time, so the page shows the counter before Pyodide has loaded and then [hydrates](concepts/server-rendering.md) it. Outside the production bootstrap, mount a view yourself with [`render`][wybthon.render].

## Add props

A component that takes inputs declares them on a [`Props`][wybthon.Props] class. Each [`Prop[T]`][wybthon.Prop] field reads as an accessor, and pyright and mypy check every call without a plugin:

```python
from wybthon import Prop, Props, button, component, create_signal, div, h1, p, prop


class CounterProps(Props):
    label: Prop[str]
    initial: Prop[int] = prop(default=0)


@component
def Counter(props: CounterProps):
    count, set_count = create_signal(props.initial.peek())
    return div(
        p(props.label, t": {count}"),
        button("+1", on_click=lambda: set_count(lambda n: n + 1)),
    )


@component
def App():
    return div(h1("My Wybthon app"), Counter(label="Clicks", initial=5))
```

See [Components](concepts/components.md) for children, callbacks, and defaults.

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

The output in `dist/` contains prerendered pages, hashed source archives, a browser bootstrap, and an asset manifest. Production builds turn dev mode off before your application imports, so dev-only checks and warnings don't ship. Deploy those files to a static host. See [Deployment](guides/deployment.md) for base paths, pinned dependencies, lazy chunks, and route fallback configuration.

Continue with the [mental model](concepts/mental-model.md), [stores](concepts/stores.md), and [runtime contracts](concepts/runtime-contracts.md).
