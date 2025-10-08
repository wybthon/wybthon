### Demo App

The demo is served from `examples/demo/`.

- `index.html` loads `bootstrap.js`
- `bootstrap.js` loads Pyodide, mounts the library from `src/wybthon/`, and copies demo files under `/app` inside Pyodide FS, then calls `app.main.main()`

Folders under `examples/demo/app/` mirror routes and components.

#### Routing and lazy loading

Routes are defined in `examples/demo/app/routes.py`. The demo showcases lazy loading using `load_component()` and `lazy()`:

```12:36:examples/demo/app/routes.py
from app.errors.page import Page as ErrorsPage
from app.fetch.page import FetchPage
from app.forms.page import FormsPage
from app.page import Page as HomePage
from wybthon import Route, lazy, load_component


def _AboutLazy():
    return ("app.about.page", "Page")


def _TeamLazy():
    return ("app.about.team.page", "Page")


# Example of eager dynamic loader (resolves at route creation time)
Docs = load_component("app.docs.page", "Page")


def create_routes():
    return [
        Route(path="/", component=lambda p: HomePage(p)),
        Route(
            path="/about",
            component=lazy(_AboutLazy),
            children=[
                Route(path="team", component=lazy(_TeamLazy)),
            ],
        ),
        Route(path="/fetch", component=FetchPage),
        Route(path="/forms", component=FormsPage),
        Route(path="/errors", component=lambda p: ErrorsPage(p)),
        Route(path="/docs/*", component=Docs),
    ]
```

We also preload the Team route when the user hovers the link in the nav for a snappier transition:

```1:40:examples/demo/app/components/nav.py
from wybthon import Link, h, preload_component


def Nav(props):
    base_path = props.get("base_path")
    # Hint: Preload team route on nav hover to improve perceived navigation time
    def on_hover_team(_evt):
        try:
            preload_component("app.about.team.page", "Page")
        except Exception:
            pass
    return h(
        "nav",
        {"class": "nav"},
        h(Link, {"to": "/", "base_path": base_path, "class": "nav-link", "class_active": "active"}, "Home"),
        " | ",
        h(Link, {"to": "/about", "base_path": base_path, "class": "nav-link", "class_active": "active"}, "About"),
        " (",
        h(
            Link,
            {
                "to": "/about/team",
                "base_path": base_path,
                "class": "nav-link",
                "class_active": "active",
                "on_mouseenter": on_hover_team,
            },
            "Team",
        ),
        ")",
        " | ",
        h(Link, {"to": "/fetch", "base_path": base_path, "class": "nav-link", "class_active": "active"}, "Fetch"),
        " | ",
        h(Link, {"to": "/forms", "base_path": base_path, "class": "nav-link", "class_active": "active"}, "Forms"),
        " | ",
        h(Link, {"to": "/errors", "base_path": base_path, "class": "nav-link", "class_active": "active"}, "Errors"),
        " | ",
        h(Link, {"to": "/docs", "base_path": base_path, "class": "nav-link", "class_active": "active"}, "Docs"),
        " (",
        h(
            Link,
            {"to": "/docs/guide/intro", "base_path": base_path, "class": "nav-link", "class_active": "active"},
            "guide/intro",
        ),
        ")",
        " | ",
        h(
            Link,
            {"to": "/about", "base_path": base_path, "replace": True, "class": "nav-link", "class_active": "active"},
            "About (replace)",
        ),
    )
```

#### Suspense for loading UI

The Fetch page uses `Suspense` to show a fallback while its `use_resource` is loading and keeps the previous content on reloads:

```1:80:examples/demo/app/fetch/page.py
from wybthon import Component, Suspense, h, use_resource

class FetchPage(Component):
    # ... see source for full example ...
    def render(self):
        return h(
            "div",
            {},
            h("h3", {}, "Async Fetch Demo"),
            h(Suspense, {"resource": self.res, "fallback": h("p", {}, "Loading..."), "keep_previous": True}, ...),
        )
```

This mirrors how you'd code-split larger apps and warm the import cache based on intent.
