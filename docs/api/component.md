### wybthon.component

::: wybthon.component

#### What's in this module

The [`@component`][wybthon.component] decorator turns a function into a
run-once [`Component`][wybthon.Component]. The body executes a single
time when the component mounts and returns a tree. Inputs are declared
on a [`Props`][wybthon.Props] subclass and arrive as one typed
parameter; later prop changes flow into its accessors without re-running
the body. Calling a component with keyword arguments returns a `VNode`,
so trees compose like any other element.

| Name | Description |
| --- | --- |
| [`component`][wybthon.component] | Decorator producing a `Component` from a function with one `Props`-annotated parameter, or none. |
| [`Component`][wybthon.Component] | Callable wrapper; `Counter(label="Clicks")` returns a `VNode`. Type checkers see the call as constructing the props class. |

#### Declaring props

- **`Prop[T]` fields** are reactive. The parent may pass a value, an
  accessor, or a zero-argument function, and reading `props.label`
  returns an [`Accessor`][wybthon.Accessor]. Declare defaults with
  [`prop(default=...)`][wybthon.prop] or `prop(default_factory=...)`;
  checkers only see the default when it's passed by keyword.
- **Plain fields** (any other annotation) hold data the parent passes
  through untouched, such as callbacks. Reading one returns the value
  as passed and never calls it.
- **[`ParentProps`][wybthon.ParentProps]** declares `children`. Pass
  children as the `children` keyword, or with item syntax:
  `Card(title="Hi")[p("a"), p("b")]`.
- **`key=`** is accepted by every component.
- A component with no inputs takes no parameters.

In dev mode, an unknown prop or a missing required one raises
`TypeError` at the call site. There's no `**rest`; to forward
attributes, spread a [`merge`][wybthon.merge] or [`omit`][wybthon.omit]
view onto an element.

```python
from collections.abc import Callable

from wybthon import ParentProps, Prop, Props, button, component, create_signal, div, h2, omit, p, prop


class CounterProps(Props):
    label: Prop[str] = prop(default="Count")
    initial: Prop[int] = prop(default=0)
    on_change: Callable[[int], None] | None = None  # plain field: never called by the read


@component
def Counter(props: CounterProps):
    count, set_count = create_signal(props.initial.peek())  # one-time read: use .peek()

    def increment():
        set_count(lambda n: n + 1)
        if props.on_change is not None:
            props.on_change(count.peek() + 1)

    return div(
        p(props.label, ": ", count),  # accessors placed in the tree become holes
        button("+", on_click=increment),
    )


class CardProps(ParentProps):
    title: Prop[str]
    class_: Prop[str] = prop(default="card")


@component
def Card(props: CardProps):
    return div(h2(props.title), props.children, **omit(props, "title", "children"))


Counter(initial=5, label="Clicks", on_change=print)
Card(title=lambda: heading())[p("body text")]  # accessors stay live
```

Reading a prop or signal at the top level of the body freezes the value
and warns in dev mode; call it inside a hole, memo, or effect, or make
the one-time read explicit with `.peek()`.

#### See also

- [Concepts: Components](../concepts/components.md)
- [Guides: Authoring patterns](../guides/authoring-patterns.md)
- [Guides: Typing](../guides/typing.md)
- [`Prop`][wybthon.Prop], [`Props`][wybthon.Props], [`ParentProps`][wybthon.ParentProps], [`prop`][wybthon.prop], [`merge`][wybthon.merge], [`omit`][wybthon.omit], [`children`][wybthon.children]
