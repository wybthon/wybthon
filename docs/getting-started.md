# Getting started

Wybthon runs client-side Python through Pyodide. Components run once; accessors and explicit expressions update their reactive parts. The renderer batches a Virtual DOM's mutations into JavaScript.

## Create an application

Install Python 3.12 or later and Wybthon:

```bash
python -m pip install wybthon
wyb init my-app
cd my-app
wyb dev --open
```

The generated project has `app/main.py`, `index.html`, and `wybthon.toml`. The development server builds the app and reloads the browser after source, configuration, or public asset changes. Pyodide requires a network connection on the first load unless you host the runtime locally.

## Write a component

```python
from wybthon import button, component, create_signal, div, h1

@component
def App():
    count, set_count = create_signal(0)
    return div(
        h1("My Wybthon app"),
        button(
            lambda: f"Count: {count()}",
            on_click=lambda event: set_count(lambda n: n + 1),
        ),
    )

def app():
    return App()
```

`count` is an accessor. `lambda: f"Count: {count()}"` is a tracked expression; reading `count()` directly during setup would capture a one-time value. Event writes batch automatically.

`app` is the entry point named in `wybthon.toml`. It returns the root view, and the bootstrap mounts it into `#app`. The generated project prerenders `/` at build time, so the page shows the counter before Pyodide has loaded and then [hydrates](concepts/server-rendering.md) it. Outside the production bootstrap, mount a view yourself with [`render`][wybthon.render].

## Build and preview

```bash
wyb build
wyb preview
```

The output in `dist/` contains prerendered pages, hashed source archives, a browser bootstrap, and an asset manifest. Deploy those files to a static host. See [Deployment](guides/deployment.md) for base paths, pinned dependencies, lazy chunks, and route fallback configuration.

Continue with the [mental model](concepts/mental-model.md), [stores](concepts/stores.md), and [runtime contracts](concepts/runtime-contracts.md).
