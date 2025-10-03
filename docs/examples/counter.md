### Counter

Demonstrates state updates with `signal` inside a class component.

```python
from wybthon import Component, h, signal

class Counter(Component):
    def __init__(self, props):
        super().__init__(props)
        self.count = signal(0)

    def render(self):
        return h("div", {},
                 h("p", {}, f"Count: {self.count.get()}"),
                 h("button", {"on_click": lambda e: self.count.set(self.count.get() + 1)}, "Increment"))
```

Function component variant (stateless presentation wrapping a class instance is recommended for state, but for simple counters you can inline):

```python
from wybthon import h

def CounterFn(props):
    # This example demonstrates a presentational wrapper around the class version.
    # Prefer class components for stateful logic.
    from app.components.counter import Counter as CounterClass
    return h(CounterClass, props)
```

See also: [Authoring Patterns](../guides/authoring-patterns.md)
