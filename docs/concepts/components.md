### Components

Wybthon supports both function and class components.

#### Function components with `@component` (recommended)

The `@component` decorator lets you define components using Pythonic keyword
arguments instead of a raw props dict:

```python
from wybthon import component, div, h2

@component
def Hello(name: str = "world"):
    return h2(f"Hello, {name}!", class_name="greeting")
```

Props become regular Python parameters with type annotations and defaults.
This makes components self-documenting and enables static type checking.

Stateful components work naturally with hooks:

```python
from wybthon import button, component, div, p, use_state

@component
def Counter(initial: int = 0, label: str = "Count"):
    count, set_count = use_state(initial)
    return div(
        p(f"{label}: {count}"),
        button("+1", on_click=lambda e: set_count(lambda c: c + 1)),
    )
```

**Children** are received via a `children` parameter:

```python
from wybthon import component, h3, section

@component
def Card(title: str = "", children=None):
    kids = children if isinstance(children, list) else ([children] if children else [])
    return section(h3(title), *kids, class_name="card")
```

**Direct calls** with keyword args return a `VNode`, so you can compose
components without `h()`:

```python
Counter(initial=5, label="Score")
Card("child1", "child2", title="My Card")   # positional args become children
```

The component still works with `h()` as usual:

```python
from wybthon import h

h(Counter, {"initial": 5, "label": "Score"})
```

See: [Hooks](hooks.md) for the full hooks API.

#### Traditional function components

You can still define components the traditional way with a `props` dict.
This style is fully supported and does not require a decorator:

```python
from wybthon import div, h2

def Hello(props):
    name = props.get("name", "world")
    return h2(f"Hello, {name}!", class_name="greeting")
```

The HTML helpers accept **children as positional arguments** and **props as keyword arguments**. Use `class_name` instead of `class` (reserved word in Python) and `html_for` instead of `for`.

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

@component
def PageContent():
    return Fragment(
        h1("Title"),
        p("Body text here."),
    )
```

#### `memo`

Wrap a function component with `memo` to skip re-renders when its props
have not changed (shallow identity comparison by default):

```python
from wybthon import component, memo, h

@component
def ExpensiveList(items=None):
    items = items or []
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
from wybthon import component, create_portal, h

@component
def Modal():
    return h("div", {},
        h("p", {}, "Page content"),
        create_portal(
            h("div", {"class": "modal"}, "I appear in #modal-root!"),
            "#modal-root",
        ),
    )
```

The second argument is an `Element` or a CSS selector string.

Both function and class styles are fully supported. For new code, **`@component` decorated functions with hooks** are recommended for their conciseness, type safety, and composability.

See the guide for recommended patterns around props, state, children, cleanup, and context, and a runnable example page:

- Guide: [Authoring Patterns](../guides/authoring-patterns.md)
- Example: [Authoring Patterns Example](../examples/authoring-patterns.md)
