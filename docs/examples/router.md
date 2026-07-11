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
from wybthon import lazy
from wybthon.router import Router, Route

Docs = lazy(lambda: ("app.docs.page", "Page"))

def TeamLazy():
    return ("app.about.team.page", "Page")

Team = lazy(TeamLazy)

routes = [
    Route(path="/docs/*", component=Docs),
    Route(path="/about/team", component=Team),
]

# Preload on some user intent (e.g., hover)
def on_hover_team(_evt):
    Team.preload()
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

## Next steps

- Read the [Router](../concepts/router.md) concept page.
- See [Suspense and Lazy Loading](../concepts/suspense-lazy.md) for code-splitting routes.
- Browse the [`router`][wybthon.router] and [`router_core`][wybthon.router_core] APIs.
