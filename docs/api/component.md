### wybthon.component

::: wybthon.component

#### `@component`

Decorator that enables Pythonic keyword-argument props for function components.

**Stateless** — return a `VNode` directly:

```python
from wybthon import component, p

@component
def Greeting(name: str = "world"):
    return p(f"Hello, {name}!")
```

**Stateful** — create signals and return a render function:

```python
from wybthon import component, create_signal, div, p

@component
def Counter(initial: int = 0):
    count, set_count = create_signal(initial)
    def render():
        return div(p(f"Count: {count()}"))
    return render
```

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
h(Counter, {"initial": 5})
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
