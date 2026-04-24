### Error Boundary

Catch render errors and show a fallback. Reset via a button or key changes.

```python
from wybthon import ErrorBoundary, h, create_signal

def Boom(_props):
    raise RuntimeError("boom")

def Fallback(err, reset):
    return h("div", {"style": {"color": "crimson"}},
             h("p", {}, f"Caught: {err}"),
             h("button", {"on_click": lambda e: reset()}, "Retry"))

view = h(ErrorBoundary, {"fallback": Fallback}, h(Boom, {}))

# Auto-reset when key changes
key, set_key = create_signal(0)
view_keyed = h(ErrorBoundary, {"fallback": Fallback, "reset_key": lambda: key()}, h(Boom, {}))
```

## Next steps

- Read the [Error Boundaries](../concepts/error-boundaries.md) concept page.
- See the [`error_boundary`][wybthon.error_boundary] API reference.
- Combine with [Suspense](../concepts/suspense-lazy.md) for async failure handling.
