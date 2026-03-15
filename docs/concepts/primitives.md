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

#### `get_props`

Return a reactive getter for the current component's props.  Useful in
stateful components that need to react when a parent changes props:

```python
from wybthon import component, create_effect, get_props

@component
def Search(query: str = ""):
    props = get_props()
    create_effect(lambda: print("query changed:", props()["query"]))

    def render():
        return ...
    return render
```

