### Error Boundaries

`ErrorBoundary` catches errors thrown during render of its subtree and renders a fallback. You can reset the boundary imperatively or by changing a `reset_key(s)` prop.

```python
from wybthon import ErrorBoundary, h

def Failing(_props):
    raise RuntimeError("boom")

def fallback(err, reset):
    # reset is provided for convenience; you can also use reset_key(s)
    return h("div", {"class": "error"},
             h("p", {}, f"Oops: {err}"),
             h("button", {"on_click": lambda e: reset()}, "Try again"))

view = h(ErrorBoundary, {"fallback": fallback}, h(Failing, {}))
```

#### Auto-reset with keys

When a `reset_key` (single) or `reset_keys` (list/tuple) value changes, the boundary clears its error and re-renders children on the next render.

```python
from wybthon import ErrorBoundary, h, create_signal

count, set_count = create_signal(0)

def Counter(_props):
    c = count()
    if c % 2 == 1:
        raise ValueError("odd!")
    return h("span", {}, f"Count: {c}")

view = h(
    "div",
    {},
    h(ErrorBoundary, {"fallback": lambda err, reset: h("span", {}, f"Err: {err}")}, h(Counter, {})),
    h("button", {"on_click": lambda e: set_count(count() + 1)}, "+1"),
)

# Or couple the boundary to a key so it resets when `count` changes:
view_keyed = h(
    ErrorBoundary,
    {"fallback": lambda err, reset: h("span", {}, f"Err: {err}"), "reset_key": lambda: count()},
    h(Counter, {}),
)
```

#### on_error hook

Provide `on_error` to observe errors when they're captured by the boundary:

```python
def observe(err):
    print("Captured:", err)

view = h(ErrorBoundary, {"fallback": lambda e, r: "Oops", "on_error": observe}, h(Failing, {}))
```

#### The `on_error` primitive

Separately from the boundary's prop, the top-level
[`on_error`][wybthon.on_error] primitive registers an error handler on
the **current reactive scope** (mirroring Solid's `onError`). Errors
raised by effects and computations created under that scope route to
the nearest ancestor handler instead of propagating:

```python
from wybthon import component, on_error

@component
def Dashboard():
    on_error(lambda exc: report_to_monitoring(exc))
    ...
```

Use `ErrorBoundary` when you need fallback UI, and `on_error` (or
[`catch_error`][wybthon.catch_error]) when you only need to observe or
log.

#### Limitations

- Only errors thrown during render of the child subtree are caught. Errors in event handlers or async tasks should be handled separately.

## Next steps

- See the [`error_boundary`][wybthon.error_boundary] API reference.
- Read [Suspense and Lazy Loading](suspense-lazy.md) for async error handling.
- Walk through the [Error boundary example](../examples/errors.md).
