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

Lazily load route components with [`lazy`][wybthon.lazy] to reduce initial load time. The loader returns a module path (or `(module_path, attr)` tuple), a module, or a component, and it may be async.

```python
from wybthon import lazy
from wybthon.router import Route

Docs = lazy(lambda: ("examples.demo.app.docs.page", "Page"))

def AboutLazy():
    return ("examples.demo.app.about.page", "Page")

About = lazy(AboutLazy)

routes = [
    Route(path="/docs/*", component=Docs),
    Route(path="/about", component=About),
]
```

Preload components ahead of time (e.g., on hover) to hide load time:

```python
def on_hover_about(_evt):
    About.preload()
```

Notes for Pyodide:

- Ensure the module is available in the Pyodide filesystem or installed via `micropip`. Static bundling is recommended for demo apps.
- Dynamic imports are synchronous from Python's perspective but may involve underlying network fetches when using `micropip`. Use `.preload()` to warm caches before navigation.

Migration notes:

- Prior versions didn't include `Link` active styling. If you previously computed active state manually, you can remove that logic and rely on `Link`'s built-in active class.
- Use the new `replace=True` option on both `Link` and `navigate()` when you want to update the URL without adding a history entry (e.g., tab switches).

## Next steps

- Walk through the [Router example](../examples/router.md).
- See [Suspense and Lazy Loading](suspense-lazy.md) for code-splitting.
- Browse the [`router`][wybthon.router] and [`router_core`][wybthon.router_core] API references.
