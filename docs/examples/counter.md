### Counter

#### `@component` with hooks (recommended)

```python
from wybthon import button, component, div, p, use_effect, use_state

@component
def Counter(initial: int = 0):
    count, set_count = use_state(initial)

    def on_mount():
        print("Counter mounted with initial count:", count)
    use_effect(on_mount, [])

    return div(
        p(f"Count: {count}"),
        button("Increment", on_click=lambda e: set_count(lambda c: c + 1)),
        class_name="counter",
    )
```

#### Traditional function component with hooks

```python
from wybthon import button, div, p, use_effect, use_state

def Counter(props):
    count, set_count = use_state(0)

    def on_mount():
        print("Counter mounted with initial count:", count)
    use_effect(on_mount, [])

    return div(
        p(f"Count: {count}"),
        button("Increment", on_click=lambda e: set_count(lambda c: c + 1)),
        class_name="counter",
    )
```

#### Class component variant

```python
from wybthon import Component, button, div, p, signal

class Counter(Component):
    def __init__(self, props):
        super().__init__(props)
        self.count = signal(0)

    def render(self):
        return div(
            p(f"Count: {self.count.get()}"),
            button("Increment", on_click=lambda e: self.count.set(self.count.get() + 1)),
            class_name="counter",
        )
```

See also: [Hooks](../concepts/hooks.md) · [Authoring Patterns](../guides/authoring-patterns.md)
