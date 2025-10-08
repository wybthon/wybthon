### Error Boundary

Catch render errors and show a fallback. Reset via a button or key changes.

```python
from wybthon import ErrorBoundary, h, signal

def Boom(_props):
    raise RuntimeError("boom")

def Fallback(err, reset):
    return h("div", {"style": {"color": "crimson"}},
             h("p", {}, f"Caught: {err}"),
             h("button", {"on_click": lambda e: reset()}, "Retry"))

view = h(ErrorBoundary, {"fallback": Fallback}, h(Boom, {}))

# Auto-reset when key changes
key_sig = signal(0)
view_keyed = h(ErrorBoundary, {"fallback": Fallback, "reset_key": lambda: key_sig.get()}, h(Boom, {}))
```
