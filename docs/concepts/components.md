### Components

Wybthon uses function components exclusively, following the SolidJS model.

#### Function components with `@component` (recommended)

The `@component` decorator lets you define components using Pythonic keyword
arguments instead of a raw props dict:

```python
from wybthon import component, div, h2

@component
def Hello(name: str = "world"):
    return h2(f"Hello, {name()}!", class_name="greeting")
```

Props become regular Python parameters with type annotations and defaults.
This makes components self-documenting and enables static type checking.

**Stateless** components return a `VNode` directly and re-render when the
parent passes new props:

```python
@component
def Greeting(name: str = "world"):
    return p(f"Hello, {name()}!")
```

**Stateful** components create signals during setup and return a *render
function*.  Setup runs once; the render function re-runs when signals change:

```python
from wybthon import button, component, create_signal, div, p

@component
def Counter(initial: int = 0):
    count, set_count = create_signal(initial())

    def render():
        return div(
            p(f"Count: {count()}"),
            button("+1", on_click=lambda e: set_count(count() + 1)),
        )
    return render
```

**Children** are received via a `children` parameter:

```python
from wybthon import component, h3, section

@component
def Card(title: str = "", children=None):
    kids = children()
    kids = kids if isinstance(kids, list) else ([kids] if kids else [])
    return section(h3(title()), *kids, class_name="card")
```

**Direct calls** with keyword args return a `VNode`, so you can compose
components without `h()`:

```python
Counter(initial=5)
Card("child1", "child2", title="My Card")   # positional args become children
```

The component still works with `h()` as usual:

```python
from wybthon import h

h(Counter, {"initial": 5})
```

See: [Primitives](primitives.md) for the full signals-first API.

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
    its = items() or []
    return h("ul", {}, *[h("li", {}, str(i)) for i in its])

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

#### Flow control

Wybthon provides SolidJS-style flow control components for declarative
rendering logic:

```python
from wybthon import Show, For, Switch, Match

# Conditional rendering
Show(is_logged_in(), p("Welcome!"), fallback=p("Please log in"))

# List rendering (keyed)
For(items(), lambda item, idx: li(item, key=idx()))

# Multi-branch matching
Switch(
    Match(status() == "loading", p("Loading...")),
    Match(status() == "error", p("Error!")),
    Match(status() == "ready", p("Ready")),
    fallback=p("Unknown"),
)
```

See the guide for recommended patterns around props, state, children, cleanup, and context:

- Guide: [Authoring Patterns](../guides/authoring-patterns.md)
- Example: [Authoring Patterns Example](../examples/authoring-patterns.md)
