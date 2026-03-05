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

#### `memo`

Wrap a function component with `memo` to skip re-renders when its props
have not changed (shallow identity comparison by default):

```python
from wybthon import memo, h

def ExpensiveList(props):
    items = props.get("items", [])
    return h("ul", {}, *[h("li", {}, str(i)) for i in items])

MemoList = memo(ExpensiveList)
```

Pass a custom comparison function for deeper control:

```python
MemoList = memo(ExpensiveList, are_props_equal=lambda old, new: old["items"] == new["items"])
```

#### `forward_ref`

Use `forward_ref` to create a component that can receive a `ref` prop
and forward it to a child element:

```python
from wybthon import forward_ref, h

def _render(props, ref):
    return h("input", {"type": "text", "ref": ref, "class": "fancy-input"})

FancyInput = forward_ref(_render)

# Usage: h(FancyInput, {"ref": my_ref})
```

The wrapped function receives `(props, ref)` instead of `(props,)`.
When no `ref` is provided, `ref` is `None`.

#### `create_portal`

Use `create_portal` to render children into a DOM node outside the
parent component's hierarchy — ideal for modals, tooltips, and overlays:

```python
from wybthon import create_portal, h, Element

def Modal(props):
    return h("div", {},
        h("p", {}, "Page content"),
        create_portal(
            h("div", {"class": "modal"}, "I appear in #modal-root!"),
            "#modal-root",
        ),
    )
```

The second argument is an `Element` or a CSS selector string.

Both styles are fully supported. For new code, **function components with hooks** are recommended for their conciseness and composability.

See the guide for recommended patterns around props, state, children, cleanup, and context, and a runnable example page:

- Guide: [Authoring Patterns](../guides/authoring-patterns.md)
- Example: [Authoring Patterns Example](../examples/authoring-patterns.md)
