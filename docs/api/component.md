### wybthon.component

::: wybthon.component

#### `@component`

Decorator that enables Pythonic keyword-argument props for function components.

```python
from wybthon import component, div, p, use_state

@component
def Counter(initial: int = 0, label: str = "Count"):
    count, set_count = use_state(initial)
    return div(p(f"{label}: {count}"))
```

The decorator inspects the function signature and automatically extracts
matching props as keyword arguments when the VDOM engine calls the component.
Default values from the signature are used when a prop is not provided.

**Children** are available via a `children` parameter:

```python
@component
def Card(title: str = "", children=None):
    kids = children or []
    return section(h3(title), *kids)
```

**Direct calls** with keyword arguments return a `VNode`:

```python
Counter(initial=5)
Card("child1", "child2", title="My Card")
```

The component still works with `h()`:

```python
h(Counter, {"initial": 5, "label": "Score"})
```

#### forward_ref

`forward_ref(render_fn)` creates a component that receives a `ref` prop and forwards it to a child element.

The wrapped function receives `(props, ref)` instead of `(props,)`.

```python
from wybthon import forward_ref, h

FancyInput = forward_ref(lambda props, ref: h("input", {"type": "text", "ref": ref, **props}))

# Usage
h(FancyInput, {"ref": my_ref, "placeholder": "Type here..."})
```
