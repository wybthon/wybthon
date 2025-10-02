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

> TODO: Add function component variant and tests.
