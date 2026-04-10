### Primitives

Wybthon uses a **signals-first** reactive model inspired by SolidJS.
Components can be **stateless** (return a VNode directly) or **stateful**
(create signals during a one-time setup phase and return a render function
that re-runs automatically when signals change).

---

#### `create_signal`

Create a reactive signal.  Returns `(getter, setter)`.

```python
from wybthon import component, create_signal, div, p

@component
def Counter(initial: int = 0):
    count, set_count = create_signal(initial)

    def render():
        return div(
            p(f"Count: {count()}"),
        )
    return render
```

Optional keyword **`equals`** controls when subscribers run: default skips notification when the new value compares equal to the old (`==`); `equals=False` notifies on every `set()`; `equals=comparator` with `comparator(old, new) -> bool` skips when the comparator returns `True` (treat as “same”).

The setter accepts a plain value:

```python
set_count(42)
```

Signals created during setup persist for the lifetime of the component --
no cursor system, no "rules of hooks".

---

#### `create_effect`

Create an auto-tracking reactive effect.  The effect runs immediately and
re-runs whenever any signal it reads changes.

```python
from wybthon import component, create_effect, create_signal

@component
def Logger():
    count, set_count = create_signal(0)

    create_effect(lambda: print("count is now", count()))

    def render():
        return ...
    return render
```

Use `on_cleanup` inside a `create_effect` callback to register cleanup
that runs before each re-execution and on disposal:

```python
def tracked():
    val = count()
    on_cleanup(lambda: print(f"cleaning up for {val}"))

create_effect(tracked)
```

Effects can also receive the previous return value as an argument:

```python
create_effect(lambda prev: (print(f"was {prev}, now {count()}"), count())[-1])
```

---

#### `create_memo`

Create an auto-tracking computed value.  Returns a getter function that
re-computes only when its dependencies change.

```python
doubled = create_memo(lambda: count() * 2)
print(doubled())  # reactive read
```

---

#### `on_mount`

Register a callback to run once after the component mounts.

```python
from wybthon import component, on_mount

@component
def MyComponent():
    on_mount(lambda: print("Component is in the DOM!"))

    def render():
        return ...
    return render
```

---

#### `on_cleanup`

Register a cleanup callback.

- Inside a component's setup phase: runs when the component unmounts.
- Inside a `create_effect` callback: runs before each re-execution and
  on disposal.

```python
from wybthon import component, on_cleanup, on_mount

@component
def Timer():
    on_mount(lambda: start_timer())
    on_cleanup(lambda: stop_timer())

    def render():
        return ...
    return render
```

---

#### Reactive props

With `@component`, parameters are **plain Python values**. Stateless
components re-run their body with fresh values when the parent updates
props. **Stateful** components run setup once: parameter values are the
initial snapshot only.

For reactive reads of individual props after setup (effects, memos, or
when you need the latest prop inside a long-lived setup callback), call
`get_props()` once and use the **`ReactiveProps`** proxy — `props.name` or
`props["name"]` tracks that prop:

```python
from wybthon import component, create_effect, get_props

@component
def Search(query: str = ""):
    props = get_props()
    create_effect(lambda: print("query changed:", props.query))

    def render():
        return ...
    return render
```

See also: [Reactivity API](../api/reactivity.md) for `get_owner` /
`run_with_owner` (async boundaries) and `children(fn)` for memoized
children resolution.

---

#### `map_array`

Keyed reactive list mapping with stable per-item scopes.  Items are
matched by reference identity — the mapping callback runs **once** per
unique item.  Removed items have their scopes disposed.

```python
from wybthon import create_signal, map_array

items, set_items = create_signal(["A", "B", "C"])
mapped = map_array(items, lambda item, idx: f"{idx()}: {item()}")
# mapped() → ["0: A", "1: B", "2: C"]
```

---

#### `index_array`

Index-keyed reactive list mapping with stable per-index scopes.  Each
slot has a reactive item signal that updates when the value at that
position changes.  The index is a plain `int`.

```python
from wybthon import create_signal, index_array

items, set_items = create_signal(["A", "B", "C"])
mapped = index_array(items, lambda item, idx: f"[{idx}] {item()}")
# mapped() → ["[0] A", "[1] B", "[2] C"]
```

---

#### `create_selector`

Efficient selection signal for O(1) selection tracking.  Returns
`is_selected(key) → bool` — only effects for the previous and new
key are notified.

```python
from wybthon import create_signal, create_selector

selected, set_selected = create_signal(1)
is_selected = create_selector(selected)

is_selected(1)   # True
is_selected(2)   # False
set_selected(2)  # only keys 1 and 2 fire
```

