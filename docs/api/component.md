### wybthon.component

::: wybthon.component

#### `@component`

Decorator that turns a function into a Wybthon component with
**fully-reactive props**.

**Each parameter is a reactive accessor**, a zero-arg callable.

* Pass it directly into the tree to create a reactive auto-hole.
* Call it (`name()`) to read the current value (tracked when called
  inside an effect or hole).
* Wrap with [`untrack`][wybthon.untrack] for a snapshot read.

```python
from wybthon import component, p

@component
def Greeting(name="world"):
    # ``name`` is a getter; passing it as a child becomes a reactive hole.
    return p("Hello, ", name, "!")
```

**Stateful** components create signals during setup and embed reactive
holes (signal getters or `dynamic(lambda: ...)`).  The body runs once;
seed local state from props using ``untrack``:

```python
from wybthon import component, create_signal, div, p, span, untrack

@component
def Counter(initial=0):
    count, set_count = create_signal(untrack(initial))
    return div(p("Count: ", span(count)))
```

**Children** is a normal prop, also a reactive accessor.  Most
layouts read children once at setup; wrap with `untrack`:

```python
from wybthon import component, h3, section, untrack

@component
def Card(title="", children=None):
    kids = untrack(children) if callable(children) else children
    if kids is None:
        kids = []
    if not isinstance(kids, list):
        kids = [kids]
    return section(h3(title), *kids, class_="card")
```

For memoized, reactive resolution of `children` (Solid-style), use the
`children(fn)` helper with `get_props()`. See [Reactivity](reactivity.md).

**Direct calls** with keyword arguments return a `VNode`:

```python
Counter(initial=5)
Card("child1", "child2", title="My Card")
```

The component still works with `h()`:

```python
h(Counter, {"initial": 5})
```

#### Proxy mode

When the component declares a single positional parameter with no
default, the decorator passes the underlying `ReactiveProps` proxy
directly:

```python
@component
def DumpProps(props):
    # ``props.x`` -> reactive accessor; ``props.x()`` -> current value.
    return p(dynamic(lambda: ", ".join(sorted(list(props)))))
```

Use [`get_props`](reactivity.md) from inside any kwarg-style component
to obtain the same proxy.

#### forward_ref

`forward_ref(render_fn)` creates a component that receives a `ref` prop
and forwards it to a child element.

The wrapped function receives `(props, ref)` instead of `(props,)`,
and `ref` is **stripped** from props (matching React's `forwardRef`
semantics).

```python
from wybthon import forward_ref, h

FancyInput = forward_ref(lambda props, ref: h("input", {"type": "text", "ref": ref, "class_": "fancy"}))

h(FancyInput, {"ref": my_ref, "placeholder": "Type here..."})
```
