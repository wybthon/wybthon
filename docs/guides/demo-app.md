### Demo App

The demo is served from `examples/demo/`.

- `index.html` loads `bootstrap.js`
- `bootstrap.js` loads Pyodide, mounts the library from `src/wybthon/`, and copies demo files under `/app` inside Pyodide FS, then calls `app.main.main()`

Folders under `examples/demo/app/` mirror routes and components.

#### Routing and lazy loading

Routes are defined in `examples/demo/app/routes.py`.  Components are
passed directly; the new `@component` decorator handles the
`(props,)` calling convention used by the router:

```python
from app.errors.page import Page as ErrorsPage
from app.fetch.page import FetchPage
from app.page import Page as HomePage
from wybthon import Route, lazy, load_component


def _AboutLazy():
    return ("app.about.page", "Page")


def _TeamLazy():
    return ("app.about.team.page", "Page")


# Eager dynamic loader (resolves at route creation time).
Docs = load_component("app.docs.page", "Page")


def create_routes():
    return [
        Route(path="/", component=HomePage),
        Route(
            path="/about",
            component=lazy(_AboutLazy),
            children=[
                Route(path="team", component=lazy(_TeamLazy)),
            ],
        ),
        Route(path="/fetch", component=FetchPage),
        Route(path="/errors", component=ErrorsPage),
        Route(path="/docs/*", component=Docs),
    ]
```

The demo also preloads the Team route on hover for snappier
transitions:

```python
from wybthon import Link, component, h, nav, preload_component, untrack


@component
def Nav(base_path=None):
    bp = untrack(base_path)
    lp = {"base_path": bp, "class_": "nav-link", "class_active": "active"}

    def preload_team(_evt):
        try:
            preload_component("app.about.team.page", "Page")
        except Exception:
            pass

    return nav(
        h(Link, {**lp, "to": "/"}, "Home"),
        h(Link, {**lp, "to": "/about"}, "About"),
        h(Link, {**lp, "to": "/about/team", "on_mouseover": preload_team}, "Team"),
        h(Link, {**lp, "to": "/fetch"}, "Fetch"),
        h(Link, {**lp, "to": "/docs"}, "Docs"),
        class_="app-nav",
    )
```

#### Suspense for loading UI

The Fetch page uses `Suspense` to show a fallback while its
`create_resource` is loading, and keeps the previous content visible
on reloads:

```python
from wybthon import Suspense, component, create_resource, dynamic, h, p


@component
def FetchPage():
    res = create_resource(fetcher)

    def display_text():
        err = res.error.get()
        if err:
            return str(err)
        return res.data.get() or "No data"

    return h(Suspense, {
        "resource": res,
        "fallback": p("Loading..."),
        "keep_previous": True,
        "children": [p(dynamic(display_text))],
    })
```

This mirrors how you'd code-split larger apps and warm the import
cache based on intent.

## Next steps

- Explore the [Examples](../examples.md) for individual feature walkthroughs.
- Read [Suspense and Lazy Loading](../concepts/suspense-lazy.md).
- See the [Dev server guide](dev-server.md) for the local feedback loop.
