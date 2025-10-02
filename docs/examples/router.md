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

> TODO: Add dynamic params and query parsing example.
