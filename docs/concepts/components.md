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
        return h("div", {}, "Counter here")
```

Lifecycle hooks for class components: `on_mount`, `on_update(prev_props)`, `on_unmount`.

See the guide for recommended patterns around props, state, children, cleanup, and context, and a runnable example page:

- Guide: [Authoring Patterns](../guides/authoring-patterns.md)
- Example: [Authoring Patterns Example](../examples/authoring-patterns.md)
