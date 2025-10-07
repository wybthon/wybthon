### Router

Client-side routing with path params and query parsing.

```python
from wybthon import h
from wybthon.router import Router, Route, Link

def Home(props):
    return h("div", {}, "Home")

routes = [
    Route(path="/", component=Home),
]

app = h(Router, {"routes": routes})
```

- `navigate(path, replace=False)` updates history and `current_path`
- `Link` intercepts clicks for SPA navigation and applies an active class when matched

#### Dynamic params and queries

```python
Route(path="/users/:id", component=UserPage)
# /users/42?tab=activity → props["params"]["id"] == "42", props["query"]["tab"] == "activity"
```

#### Nested routes with `Route.children`

```python
routes = [
    Route(
        path="/about",
        component=About,
        children=[
            Route(path="team", component=Team),  # matches /about/team
        ],
    ),
]
```

#### Wildcards and 404

```python
Route(path="/docs/*", component=Docs)  # params["wildcard"] contains the trailing path or ""

app = h(Router, {"routes": routes, "not_found": NotFound})  # optional custom 404
```

#### Base path

```python
app = h(Router, {"routes": routes, "base_path": "/app"})
# Link respects base path; Link({"to": "/about"}) → href "/app/about"
```

#### Active links and replace navigation

```python
# `Link` adds `class="active"` when the current path matches its href.
h(Link, {"to": "/about", "class": "nav-link"}, "About")
# Customize class name and avoid pushing history with replace
h(Link, {"to": "/about", "class_active": "is-active", "replace": True}, "About (replace)")

# Imperative navigation
from wybthon.router import navigate
navigate("/about", replace=True)
```

#### Lazy routes and preloading

Lazily load route components to reduce initial load time. Use `load_component` for direct module paths or `lazy` for a small loader function. Both are Pyodide-compatible.

```python
from wybthon import load_component, lazy
from wybthon.router import Route

# Load a component from a module that exports Page(props)
Docs = load_component("examples.demo.app.docs.page", "Page")

# Or define a loader function returning (module_path, optional_attr)
def AboutLazy():
    return ("examples.demo.app.about.page", "Page")

routes = [
    Route(path="/docs/*", component=Docs),
    Route(path="/about", component=lazy(AboutLazy)),
]
```

Preload components ahead of time (e.g., on hover) to hide load time:

```python
from wybthon import preload_component

def on_hover_about(_evt):
    preload_component("examples.demo.app.about.page", "Page")
```

Notes for Pyodide:
- Ensure the module is available in the Pyodide filesystem or installed via `micropip`. Static bundling is recommended for demo apps.
- Dynamic imports are synchronous from Python’s perspective but may involve underlying network fetches when using `micropip`. Use `preload_component` to warm caches before navigation.

Migration notes:
- Prior versions did not include `Link` active styling. If you previously computed active state manually, you can remove that logic and rely on `Link`'s built-in active class.
- Use the new `replace=True` option on both `Link` and `navigate()` when you want to update the URL without adding a history entry (e.g., tab switches).
