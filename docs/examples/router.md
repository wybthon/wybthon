### Router

Basic routing with `Router` and `Link`.

```python
from wybthon.router import Router, Route, Link
from wybthon import h

def Home(props):
    return h("div", {}, "Home", h("div", {}, h(Link, {"to": "/about", "children": ["About"]})))

def About(props):
    return h("div", {}, "About")

routes = [
    Route(path="/", component=Home),
    Route(path="/about", component=About),
]

app = h(Router, {"routes": routes})
```

Active links and replace navigation:

```python
# Adds class="active" when matched
h(Link, {"to": "/about", "children": ["About"]})

# Custom active class and replace behavior
h(Link, {"to": "/about", "class_active": "is-active", "replace": True, "children": ["About"]})

# Imperative navigation with replace
from wybthon.router import navigate
navigate("/about", replace=True)
```

#### Lazy routes

```python
from wybthon import load_component, lazy, preload_component
from wybthon.router import Router, Route

Docs = load_component("app.docs.page", "Page")

def TeamLazy():
    return ("app.about.team.page", "Page")

routes = [
    Route(path="/docs/*", component=Docs),
    Route(path="/about/team", component=lazy(TeamLazy)),
]

# Preload on some user intent (e.g., hover)
def on_hover_team(_evt):
    preload_component("app.about.team.page", "Page")
```

Dynamic params and queries:

```python
Route(path="/users/:userId", component=User)
# /users/123?tab=info → props["params"]["userId"] == "123", props["query"]["tab"] == "info"
```

Nested and wildcard routes:

```python
routes = [
    Route(path="/about", component=About, children=[Route(path="team", component=Team)]),
    Route(path="/docs/*", component=Docs),
]

app = h(Router, {"routes": routes, "not_found": NotFound})
```
