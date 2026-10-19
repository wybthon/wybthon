### wybthon.component

::: wybthon.component

#### What's in this module

The [`@component`][wybthon.component] decorator turns a function into a
run-once [`Component`][wybthon.Component]. The body executes a single
time when the component mounts and returns a tree, usually an
[`html`][wybthon.html] template. Inputs are declared on a
[`Props`][wybthon.Props] subclass and arrive as one typed parameter;
later prop changes flow into its accessors without re-running the body.
Calling a component with keyword arguments returns a `VNode`, so trees
compose like any other node.

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
  children as the `children` keyword, with item syntax
  (`Card(title="Hi")[...]`), or as the content of a component tag in a
  template (`<{Card} title="Hi">...</{Card}>`).
- **`key=`** is accepted by every component.
- A component with no inputs takes no parameters.

In dev mode, an unknown prop or a missing required one raises
`TypeError` at the call site. There's no `**rest`; to forward
attributes, spread a [`merge`][wybthon.merge] or [`omit`][wybthon.omit]
view onto an element (`<div {omit(props, "title")}>` in a template).

```python
from collections.abc import Callable

from wybthon import ParentProps, Prop, Props, component, create_signal, html, omit, prop


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

    # Accessors placed in the template become holes.
    return html(t"""
      <div>
        <p>{props.label}: {count}</p>
        <button onclick={increment}>+</button>
      </div>
    """)


class CardProps(ParentProps):
    title: Prop[str]
    class_: Prop[str] = prop(default="card")


@component
def Card(props: CardProps):
    return html(t"<div {omit(props, 'title', 'children')}><h2>{props.title}</h2>{props.children}</div>")


heading, set_heading = create_signal("Hello")

Counter(initial=5, label="Clicks", on_change=print)
Card(title=heading)[html(t"<p>body text</p>")]  # an accessor stays live
html(t"<{Card} title={heading}><p>body text</p></{Card}>")  # the same, as a tag
```

Reading a prop or signal at the top level of the body freezes the value
and warns in dev mode; call it inside a hole, memo, or effect, or make
the one-time read explicit with `.peek()`.

#### Using components in templates

Call a component inside an interpolation, `{Counter(initial=5)}`, to
keep full type checking of its props. The tag form,
`<{Card} title="Hi">...</{Card}>` or `<{Card} />`, passes attributes as
keyword props (a hyphen becomes an underscore) and nested markup as
`children`; type checkers can't see inside the template string, so dev
mode checks its props at run time. See
[Templates](../concepts/templates.md#components-in-templates).

#### What a component costs

A component is only patched with new props when a reactive hole
re-renders a tree that contains it, or when `render` runs again into the
same container. Everywhere else (inside a template, another component's
output, a list row, or a `Show` branch) its props never change, so:

- reading a `Prop` that the parent passed as a constant subscribes to
  nothing;
- a prop passed as an accessor or zero-argument function is read
  through, so the reader subscribes to that source directly;
- a binding that reads nothing reactive is dropped after its first run.

A component whose props never change costs about what its markup costs.
Components that can be patched track one version signal per props
instance, created on the first tracked read.

A plain, undecorated function used as a tag, as in `h(fn, props)`,
receives the props dictionary and runs again when it's patched with
changed props. Use `@component` when you want typed, reactive props.

#### See also

- [Concepts: Components](../concepts/components.md)
- [Concepts: Templates](../concepts/templates.md)
- [Guides: Authoring patterns](../guides/authoring-patterns.md)
- [Guides: Typing](../guides/typing.md)
- [`Prop`][wybthon.Prop], [`Props`][wybthon.Props], [`ParentProps`][wybthon.ParentProps], [`prop`][wybthon.prop], [`merge`][wybthon.merge], [`omit`][wybthon.omit], [`children`][wybthon.children]
