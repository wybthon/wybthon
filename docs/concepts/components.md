### Components

Wybthon supports both function and class components.

#### Function components

```python
from wybthon import h

def Hello(props):
    name = props.get("name", "world")
    return h("div", {}, f"Hello {name}")
```

#### Class components

```python
from wybthon import Component, h

class Counter(Component):
    def render(self):
        return h("div", {}, "TODO: counter example here")
```

Lifecycle hooks for class components: `on_mount`, `on_update(prev_props)`, `on_unmount`.

> TODO: Add guidance on state ownership, passing children, and composition patterns.
