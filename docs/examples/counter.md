### Counter

#### `@component` with signals (new style — body runs once, hole updates)

```python
from wybthon import button, component, create_signal, div, on_mount, p, span

@component
def Counter(initial: int = 0):
    count, set_count = create_signal(initial)

    on_mount(lambda: print("Counter mounted with initial count:", count()))

    return div(
        p("Count: ", span(count.get)),                          # ← reactive hole
        button("Increment", on_click=lambda e: set_count(count() + 1)),
        class_name="counter",
    )
```

`count.get` is a zero-arg accessor.  When you embed it in the VNode
tree the reconciler wraps it in its own effect — only that text node
updates when the signal changes.  See
[Primitives → Reactive Holes](../concepts/primitives.md#reactive-holes).

#### Legacy "return render" style (still supported)

```python
from wybthon import button, component, create_signal, div, p

@component
def Counter(initial: int = 0):
    count, set_count = create_signal(initial)

    def render():
        return div(
            p(f"Count: {count()}"),
            button("Increment", on_click=lambda e: set_count(count() + 1)),
            class_name="counter",
        )
    return render
```

The legacy pattern is internally treated as a **single-root reactive
hole**: the render function becomes the getter and the entire returned
subtree is replaced when any signal it reads changes.  Prefer the new
style for finer-grained updates.

#### Traditional function component

```python
from wybthon import create_signal, div, p, button, span

count, set_count = create_signal(0)

def Counter(props):
    return div(
        p("Count: ", span(count.get)),
        button("Increment", on_click=lambda e: set_count(count() + 1)),
        class_name="counter",
    )
```

See also: [Primitives](../concepts/primitives.md) · [Authoring Patterns](../guides/authoring-patterns.md)
