### Error Boundaries

`ErrorBoundary` catches errors thrown during render of its subtree and renders a fallback.

```python
from wybthon.vdom import ErrorBoundary
from wybthon import h

def fallback(err):
    return h("div", {"class": "error"}, f"Oops: {err}")

view = h(ErrorBoundary, {"fallback": fallback, "children": ["TODO: child"]})
```

> TODO: Document reset behavior and limitations.
