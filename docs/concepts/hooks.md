### Hooks

Hooks let function components hold state, run side effects, and memoize
values — no class required.  If you have used React hooks, the API will
feel immediately familiar.

#### Rules of hooks

1. **Call hooks at the top level** of your function component.
2. **Do not** call hooks inside loops, conditions, or nested functions.
3. **Do not** call hooks outside a function component's render.

These rules exist because hooks rely on a stable call order to map each
hook call to its stored state slot.

---

#### `use_state`

Declare a piece of component-local state.  Returns `(value, setter)`.

```python
from wybthon import h, use_state

def Counter(props):
    count, set_count = use_state(0)
    return h("div", {},
        h("p", {}, f"Count: {count}"),
        h("button", {"on_click": lambda e: set_count(count + 1)}, "+1"),
    )
```

The setter accepts a plain value **or** an updater function that receives
the previous value:

```python
set_count(42)                  # set directly
set_count(lambda prev: prev+1) # updater
```

You can also pass a callable as the initial value; it will be invoked once
on the first render (lazy initialization):

```python
val, set_val = use_state(lambda: expensive_default())
```

---

#### `use_effect`

Register a side-effect that runs **after** the component renders.

| `deps` argument | Behavior |
|---|---|
| `None` (default) | Runs after **every** render |
| `[]` | Runs only on **mount** |
| `[a, b]` | Runs when `a` or `b` changes |

Return a cleanup function from the effect to run before the next
execution or on unmount:

```python
from wybthon import h, use_state, use_effect

def Timer(props):
    seconds, set_seconds = use_state(0)

    def setup():
        from js import setInterval, clearInterval
        from pyodide.ffi import create_proxy

        proxy = create_proxy(lambda: set_seconds(lambda s: s + 1))
        tid = setInterval(proxy, 1000)

        def cleanup():
            clearInterval(tid)
            proxy.destroy()
        return cleanup

    use_effect(setup, [])  # mount-only

    return h("p", {}, f"Elapsed: {seconds}s")
```

---

#### `use_memo`

Memoize an expensive computation.  Re-computes only when `deps` change.

```python
filtered = use_memo(lambda: [x for x in items if x.active], [items])
```

---

#### `use_ref`

Create a mutable container that persists across renders without causing
re-renders when mutated.

```python
ref = use_ref(None)
# ref.current can be read/written freely
```

---

#### `use_callback`

Memoize a callback so child components receiving it as a prop can skip
unnecessary re-renders.

```python
handle_click = use_callback(lambda e: set_count(count + 1), [count])
```

---

#### `use_reducer`

Manage complex state with a reducer function.  Returns `(state, dispatch)`.

```python
from wybthon import h, use_reducer

def reducer(state, action):
    if action["type"] == "increment":
        return {**state, "count": state["count"] + 1}
    if action["type"] == "decrement":
        return {**state, "count": state["count"] - 1}
    if action["type"] == "reset":
        return {"count": 0}
    return state

def Counter(props):
    state, dispatch = use_reducer(reducer, {"count": 0})
    return h("div", {},
        h("p", {}, f"Count: {state['count']}"),
        h("button", {"on_click": lambda e: dispatch({"type": "increment"})}, "+1"),
        h("button", {"on_click": lambda e: dispatch({"type": "decrement"})}, "-1"),
        h("button", {"on_click": lambda e: dispatch({"type": "reset"})}, "Reset"),
    )
```

An optional `init` function lazily computes the initial state:

```python
state, dispatch = use_reducer(reducer, initial_arg, init=lambda arg: {"count": arg})
```

---

#### `use_layout_effect`

Same API as `use_effect` but fires **synchronously** after all DOM
mutations, before the browser repaints.  Use this for DOM measurements
and synchronous visual updates.

```python
from wybthon import use_layout_effect, use_ref, use_state

def MeasuredBox(props):
    ref = use_ref(None)
    width, set_width = use_state(0)

    def measure():
        if ref.current is not None:
            set_width(ref.current.element.offsetWidth)

    use_layout_effect(measure, [])

    return h("div", {"ref": ref}, f"Width: {width}px")
```

---

#### Hooks vs. class components

| | Function + hooks | Class component |
|---|---|---|
| State | `use_state` | `self.count = signal(0)` |
| Side effects | `use_effect` | `on_mount` / `on_cleanup` |
| Memoization | `use_memo` | manual |
| Refs | `use_ref` | instance attributes |

Both styles are fully supported; choose whichever fits your situation.
For new code, **hooks are recommended** because they are more concise
and composable.
