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
- `Link` intercepts clicks for SPA navigation

> TODO: Document nested routes and wildcard matching.
