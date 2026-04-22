### Primitives

Wybthon uses a **signals-first** reactive model inspired by SolidJS.
Component bodies run **once** at mount.  Reactivity comes from signals
read inside *reactive holes* — zero-arg callables placed inside the
returned VNode tree.  See the [Reactive Holes](#reactive-holes) section
below.

---

#### Reactive Holes

A **reactive hole** is a zero-arg callable embedded in a VNode tree
(child or prop value).  The reconciler wraps each hole in its own
effect, so the surrounding component body runs **once** while the
hole updates the DOM in place when its dependencies change.

There are three ways to create a hole:

```python
from wybthon import button, component, create_signal, div, dynamic, p, span

@component
def Demo():
    count, set_count = create_signal(0)

    return div(
        # 1) Pass a signal accessor directly:
        p("Count: ", span(count.get)),

        # 2) Wrap a derived expression with ``dynamic``:
        p(dynamic(lambda: f"Doubled: {count() * 2}")),

        # 3) Reactive prop value (any callable prop except event handlers):
        p("Status",
          class_name=lambda: "danger" if count() > 5 else "ok"),

        button("+1", on_click=lambda e: set_count(count() + 1)),
    )
```

A hole's getter may return any of:

- a string or number → rendered as a text node
- a `VNode` → mounted as the hole's subtree (replacing the previous one)
- a `Fragment` or list of VNodes → mounted as multiple roots between
  the hole's start/end anchors
- `None` → renders nothing

Holes are scoped to their owner.  Inside a hole you can use
`on_cleanup` to register teardown that runs before each re-execution
and on disposal — the same lifecycle as `create_effect`:

```python
@component
def Subscriber():
    topic, _ = create_signal("a")
    return p(
        dynamic(lambda: subscribe(topic())),  # subscribe re-runs on topic change
    )

def subscribe(topic_name):
    handle = open_subscription(topic_name)
    on_cleanup(handle.close)
    return f"listening to {topic_name}"
```

> **Why?** This is the SolidJS authoring model adapted for Pyodide.
> Components run once, so signal *creation*, event-handler *closures*,
> and lifecycle *registrations* happen exactly once — and DOM updates
> stay surgical and predictable.

---

#### `create_signal`

Create a reactive signal.  Returns `(getter, setter)`.

```python
from wybthon import component, create_signal, div, p, span

@component
def Counter(initial: int = 0):
    count, set_count = create_signal(initial)

    return div(
        p("Count: ", span(count.get)),  # ← reactive hole
    )
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
from wybthon import component, create_effect, create_signal, p

@component
def Logger():
    count, set_count = create_signal(0)

    create_effect(lambda: print("count is now", count()))

    return p(count.get)
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
from wybthon import component, on_mount, p

@component
def MyComponent():
    on_mount(lambda: print("Component is in the DOM!"))
    return p("hello")
```

---

#### `on_cleanup`

Register a cleanup callback.

- Inside a component's setup phase: runs when the component unmounts.
- Inside a `create_effect` callback or a reactive hole: runs before
  each re-execution and on disposal.

```python
from wybthon import component, div, on_cleanup, on_mount

@component
def Timer():
    on_mount(lambda: start_timer())
    on_cleanup(lambda: stop_timer())
    return div("...")
```

---

#### Reactive props

With `@component`, parameters are **plain Python values** captured
once at setup time.  Because the component body runs once, parameter
values reflect the initial snapshot.

For reactive reads of individual props (effects, memos, or reactive
holes), call `get_props()` once and use the **`ReactiveProps`** proxy
— `props.name` or `props["name"]` tracks that prop:

```python
from wybthon import component, create_effect, get_props, p

@component
def Search(initial_query: str = ""):
    props = get_props()
    create_effect(lambda: print("query changed:", props.query))

    return p("Searching: ", lambda: str(props.query))
```

When a parent component wants to pass a *reactive value* to a child,
the canonical pattern is to **pass the getter**:

```python
@component
def Parent():
    name, _ = create_signal("Ada")
    return Greeting(name=name.get)   # pass the getter, not the value

@component
def Greeting(name=None):
    return p("Hello, ", name)        # ``name`` is now a reactive hole
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

