### wybthon.component

::: wybthon.component

#### What's in this module

The [`@component`][wybthon.component] decorator turns a function into a
run-once [`Component`][wybthon.Component]. The body executes a single
time when the component mounts and returns a tree, usually an
[`html`][wybthon.html] template. Inputs are declared on a
[`Props`][wybthon.Props] subclass and arrive as one typed parameter, the
counterpart of Solid's `props` object: reading `props.label` returns the
parent's current value, tracked, so later changes flow into the places
that read it without re-running the body. Calling a component with
keyword arguments returns a `VNode`, so trees compose like any other
node.

| Name | Description |
| --- | --- |
| [`component`][wybthon.component] | Decorator producing a `Component` from a function with one `Props`-annotated parameter, or none. |
| [`Component`][wybthon.Component] | Callable wrapper; `Counter(label="Clicks")` returns a `VNode`. Type checkers see the call as constructing the props class. |
| [`builtin`][wybthon.component.builtin] | Internal: marks a built-in that renders markup (`Show`, `For`, `Loading`, ...) so a compiled template builds it with getters for its dynamic arguments, as it does a component. |

#### Declaring props

- **Fields are plain annotations** (`title: str`). Reading
  `props.title` returns the value and tracks it. The parent may pass a
  value, an accessor, or a getter (what the compiler makes of
  `<{Card} title={user().name}>`); getters and accessors are unwrapped
  on read.
- **Defaults** work as in a dataclass: `step: int = 1`. Use
  [`prop(default_factory=...)`][wybthon.prop] for a mutable default
  (the factory runs once per instance); `prop(default=...)` also works.
- **Callable fields** (`Callable[...]` or `Accessor[...]`, alone or in
  a union with `None`) return what the parent passed, never calling it,
  so callbacks and accessors you mean to keep arrive intact.
- **[`ParentProps`][wybthon.ParentProps]** declares `children`. Pass
  children as the content of a component tag in a template
  (`<{Card} title="Hi">...</{Card}>`), as the `children` keyword, or
  with item syntax (`Card(title="Hi")[...]`).
- **`key=`** is accepted by every component.
- A component with no inputs takes no parameters.

In dev mode, an unknown prop or a missing required one raises
`TypeError` at the call site. There's no `**rest`; to forward
attributes, spread a [`merge`][wybthon.merge] or [`omit`][wybthon.omit]
view onto an element (`<div {omit(props, "title")}>` in a template).

```python
from collections.abc import Callable

from wybthon import ParentProps, Props, component, create_signal, html, omit, untrack


class CounterProps(Props):
    label: str = "Count"
    initial: int = 0
    on_change: Callable[[int], None] | None = None  # callable field: returned as passed


@component
def Counter(props: CounterProps):
    count, set_count = create_signal(untrack(lambda: props.initial))  # a one-time read

    def increment():
        set_count(lambda n: n + 1)
        if props.on_change is not None:
            props.on_change(count.peek() + 1)

    return html(t"""
      <div>
        <p>{props.label}: {count()}</p>
        <button onclick={increment}>+</button>
      </div>
    """)


class CardProps(ParentProps):
    title: str
    class_: str = "card"


@component
def Card(props: CardProps):
    return html(t"<div {omit(props, 'title', 'children')}><h2>{props.title}</h2>{props.children}</div>")


heading, set_heading = create_signal("Hello")

Counter(initial=5, label="Clicks", on_change=print)
html(t"<{Card} title={heading()}><p>body text</p></{Card}>")  # title stays live
html(t"{Card(title=heading(), children=html(t'<p>body text</p>'))}")  # the same, type-checked
```

Reading a reactive prop or signal at the top level of the body reads it
once and warns in dev mode; read it inside a template expression, memo,
or effect, or make the one-time read explicit with
[`untrack`][wybthon.untrack]. A prop the parent passed as a constant
can't change, so reading one doesn't warn.

#### Using components in templates

Call a component inside an interpolation, `{Counter(initial=5)}`, to
keep full type checking of its props; the compiler still passes each
dynamic argument as a getter. The tag form,
`<{Card} title="Hi">...</{Card}>` or `<{Card} />`, passes attributes as
keyword props (a hyphen becomes an underscore) and nested markup as
`children`; type checkers can't see inside the template string, so dev
mode checks its props at run time. See
[Templates](../concepts/templates.md#components-in-templates).

#### What a component costs

A component is only patched with new props when a reactive hole
re-renders a tree that contains it, or when `render` runs again into the
same container. Everywhere else (inside a template, another component's
output, a list row, or a `Show` branch) its props object never changes,
so:

- reading a prop that the parent passed as a constant subscribes to
  nothing;
- a prop passed as a getter or accessor is read through, so the reader
  subscribes to that source directly;
- a binding that reads nothing reactive never allocates a computation.

A component whose props never change costs about what its markup costs.
Components that can be patched track one version signal per props
instance, created on the first tracked read. Use
[`is_static`][wybthon.is_static] to ask whether the parent passed a
plain value for a key.

A plain, undecorated function used as a tag, as in `h(fn, props)`,
receives the props dictionary and runs again when it's patched with
changed props. Use `@component` when you want typed, reactive props.

#### See also

- [Concepts: Components](../concepts/components.md)
- [Concepts: Templates](../concepts/templates.md)
- [Concepts: Compiler](../concepts/compiler.md)
- [Guides: Authoring patterns](../guides/authoring-patterns.md)
- [Guides: Typing](../guides/typing.md)
- [`Props`][wybthon.Props], [`ParentProps`][wybthon.ParentProps], [`prop`][wybthon.prop], [`merge`][wybthon.merge], [`omit`][wybthon.omit], [`is_static`][wybthon.is_static], [`children`][wybthon.children]
