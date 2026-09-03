### wybthon.component

::: wybthon.component

#### What's in this module

The [`@component`][wybthon.component] decorator turns a function into a
run-once [`Component`][wybthon.Component]. The body executes a single
time when the component mounts and returns a tree; every parameter is
bound to a [`Prop`][wybthon.Prop] accessor, and later prop changes flow
into those accessors without re-running the body. Calling a component
with keyword arguments returns a `VNode`, so trees compose like any
other element.

| Name | Description |
| --- | --- |
| [`component`][wybthon.component] | Decorator producing a `Component` from a function. |
| [`Component`][wybthon.Component] | Callable wrapper; `Counter(initial=5)` returns a `VNode`, `.defaults` lists declared defaults. |

#### Binding rules

How a mounted component's `Props` mapping is bound to the function:

- **Named parameters** each become a `Prop`. Declare defaults with
  [`prop`][wybthon.prop] so the annotation `Prop[T]` type-checks; a plain
  default also works.
- **`**rest`** receives every undeclared prop as a `Prop`; forward it
  with `div(**rest)` or [`merge`][wybthon.merge].
- **A single parameter named `props`** with no annotation, or any
  parameter annotated `Props`, receives the whole
  [`Props`][wybthon.Props] mapping instead. A lone annotated parameter
  such as `def Card(title: Prop[str])` is an ordinary prop.
- Positional arguments in a call become the `children` prop.

```python
from wybthon import Prop, Props, button, component, create_signal, div, p, prop

@component
def Counter(initial: Prop[int] = prop(0), label: Prop[str] = prop("Count"), **rest):
    count, set_count = create_signal(initial.peek())   # one-time read: use .peek()
    return div(
        p(label, ": ", count),                          # Prop and accessor as reactive holes
        button("+", on_click=lambda e: set_count(lambda n: n + 1)),
        **rest,
    )

@component
def Card(props: Props):
    return div(props.title, props.children, class_="card")

Counter(initial=5, label="Clicks", id="main-counter")
Card("body text", title=lambda: heading())              # accessors stay live
```

Reading a prop or signal at the top level of the body freezes the value
and warns in dev mode; call it inside a hole, memo, or effect, or make
the one-time read explicit with `.peek()`.

#### See also

- [Concepts: Components](../concepts/components.md)
- [Guides: Authoring patterns](../guides/authoring-patterns.md)
- [Guides: Typing](../guides/typing.md)
- [`Prop`][wybthon.Prop], [`Props`][wybthon.Props], [`prop`][wybthon.prop], [`merge`][wybthon.merge], [`omit`][wybthon.omit]
