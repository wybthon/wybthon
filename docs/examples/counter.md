### Counter

#### `@component` with signals (recommended)

```python
from wybthon import button, component, create_signal, div, on_mount, p

@component
def Counter(initial: int = 0):
    count, set_count = create_signal(initial())

    on_mount(lambda: print("Counter mounted with initial count:", count()))

    def render():
        return div(
            p(f"Count: {count()}"),
            button("Increment", on_click=lambda e: set_count(count() + 1)),
            class_name="counter",
        )
    return render
```

#### Traditional function component

```python
from wybthon import create_signal, div, p, button

count, set_count = create_signal(0)

def Counter(props):
    return div(
        p(f"Count: {count()}"),
        button("Increment", on_click=lambda e: set_count(count() + 1)),
        class_name="counter",
    )
```

See also: [Primitives](../concepts/primitives.md) · [Authoring Patterns](../guides/authoring-patterns.md)
