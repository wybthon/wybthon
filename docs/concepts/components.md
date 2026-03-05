### Components

Wybthon supports both function and class components.

#### Function components (recommended)

```python
from wybthon import h

def Hello(props):
    name = props.get("name", "world")
    return h("div", {}, f"Hello {name}")
```

Function components can hold state and run side effects using **hooks**:

```python
from wybthon import h, use_state

def Counter(props):
    count, set_count = use_state(0)
    return h("div", {},
        h("p", {}, f"Count: {count}"),
        h("button", {"on_click": lambda e: set_count(count + 1)}, "+1"),
    )
```

See: [Hooks](hooks.md) for the full hooks API.

#### Class components

```python
from wybthon import Component, h, signal

class Counter(Component):
    def __init__(self, props):
        super().__init__(props)
        self.count = signal(0)

    def render(self):
        return h("div", {}, f"Count: {self.count.get()}")
```

Lifecycle hooks for class components: `on_mount`, `on_update(prev_props)`, `on_unmount`.

Both styles are fully supported. For new code, **function components with hooks** are recommended for their conciseness and composability.

See the guide for recommended patterns around props, state, children, cleanup, and context, and a runnable example page:

- Guide: [Authoring Patterns](../guides/authoring-patterns.md)
- Example: [Authoring Patterns Example](../examples/authoring-patterns.md)
