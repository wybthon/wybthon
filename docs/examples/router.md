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
