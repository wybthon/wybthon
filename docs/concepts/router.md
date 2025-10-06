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
