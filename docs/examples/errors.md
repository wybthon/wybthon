### Error Boundary

Catch render errors and show a fallback.

```python
from wybthon.vdom import ErrorBoundary
from wybthon import h

def Boom(props):
    raise RuntimeError("boom")

def fb(err):
    return h("div", {}, f"Oops: {err}")

view = h(ErrorBoundary, {"fallback": fb, "children": [h(Boom, {})]})
```

> TODO: Show boundary reset and nested boundaries.
