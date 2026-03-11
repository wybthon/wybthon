### Counter

#### `@component` with signals (recommended)

```python
from wybthon import button, component, create_signal, div, on_mount, p

@component
def Counter(initial: int = 0):
    count, set_count = create_signal(initial)

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
from wybthon import signal, effect, div, p, button

counter_signal = signal(0)

def Counter(props):
    return div(
        p(f"Count: {counter_signal.get()}"),
        button("Increment", on_click=lambda e: counter_signal.set(counter_signal.get() + 1)),
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

See also: [Primitives](../concepts/primitives.md) · [Authoring Patterns](../guides/authoring-patterns.md)
