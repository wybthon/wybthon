### Counter

#### Function component with hooks (recommended)

```python
from wybthon import h, use_state, use_effect

def Counter(props):
    count, set_count = use_state(0)

    def on_mount():
        print("Counter mounted with initial count:", count)
    use_effect(on_mount, [])

    return h("div", {},
        h("p", {}, f"Count: {count}"),
        h("button", {"on_click": lambda e: set_count(lambda c: c + 1)}, "Increment"),
    )
```

#### Class component variant

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

See also: [Hooks](../concepts/hooks.md) · [Authoring Patterns](../guides/authoring-patterns.md)
