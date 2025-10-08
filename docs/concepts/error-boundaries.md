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
from wybthon import ErrorBoundary, h, signal

count = signal(0)

def Counter(_props):
    c = count.get()
    if c % 2 == 1:
        raise ValueError("odd!")
    return h("span", {}, f"Count: {c}")

view = h(
    "div",
    {},
    h(ErrorBoundary, {"fallback": lambda err, reset: h("span", {}, f"Err: {err}")}, h(Counter, {})),
    h("button", {"on_click": lambda e: count.set(count.get() + 1)}, "+1"),
)

# Or couple the boundary to a key so it resets when `count` changes:
view_keyed = h(
    ErrorBoundary,
    {"fallback": lambda err, reset: h("span", {}, f"Err: {err}"), "reset_key": lambda: count.get()},
    h(Counter, {}),
)
```

#### on_error hook

Provide `on_error` to observe errors when they are captured by the boundary:

```python
def on_error(err):
    print("Captured:", err)

view = h(ErrorBoundary, {"fallback": lambda e, r: "Oops", "on_error": on_error}, h(Failing, {}))
```

#### Limitations

- Only errors thrown during render of the child subtree are caught. Errors in event handlers or async tasks should be handled separately.
