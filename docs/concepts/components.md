### Components

Wybthon supports both function and class components.

#### Function components (recommended)

Use the HTML element helpers for a clean, Pythonic syntax:

```python
from wybthon import div, h2

def Hello(props):
    name = props.get("name", "world")
    return h2(f"Hello, {name}!", class_name="greeting")
```

Function components can hold state and run side effects using **hooks**:

```python
from wybthon import button, div, p, use_state

def Counter(props):
    count, set_count = use_state(0)
    return div(
        p(f"Count: {count}"),
        button("+1", on_click=lambda e: set_count(count + 1)),
    )
```

The HTML helpers accept **children as positional arguments** and **props as keyword arguments**. Use `class_name` instead of `class` (reserved word in Python) and `html_for` instead of `for`.

You can still use `h()` for components or when you need the lower-level API:

```python
from wybthon import h

h(Counter, {"initial": 5})           # render a component
h("div", {"class": "box"}, "Hello")  # render an element (h() still works)
```

See: [Hooks](hooks.md) for the full hooks API.

#### Class components

```python
from wybthon import Component, div, p, signal

class Counter(Component):
    def __init__(self, props):
        super().__init__(props)
        self.count = signal(0)

    def render(self):
        return div(p(f"Count: {self.count.get()}"))
```

Lifecycle hooks for class components: `on_mount`, `on_update(prev_props)`, `on_unmount`.

#### Fragment

Use `Fragment` to group children without adding a visible wrapper element:

```python
from wybthon import Fragment, h1, p

def PageContent(props):
    return Fragment(
        h1("Title"),
        p("Body text here."),
    )
```

Both styles are fully supported. For new code, **function components with hooks** are recommended for their conciseness and composability.

See the guide for recommended patterns around props, state, children, cleanup, and context, and a runnable example page:

- Guide: [Authoring Patterns](../guides/authoring-patterns.md)
- Example: [Authoring Patterns Example](../examples/authoring-patterns.md)
