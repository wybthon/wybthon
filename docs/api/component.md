### wybthon.component

::: wybthon.component

#### What's in this module

The [`@component`][wybthon.component] decorator turns a function into a
run-once [`Component`][wybthon.Component]. The body executes a single
time when the component mounts and returns a tree, usually an
[`html`][wybthon.html] template. Its inputs are ordinary function
parameters, the counterpart of the properties of Solid's `props`
object: the compiler rewrites every read of a parameter in the body
into a tracked read of the parent's current value, so later changes
flow into the places that read it without re-running the body. Calling
a component returns a `VNode`, so trees compose like any other node.

| Name | Description |
| --- | --- |
| [`component`][wybthon.component] | Decorator producing a `Component` from a function whose parameters are its props. |
| [`Component`][wybthon.Component] | Callable wrapper; `Counter(label="Clicks")` returns a `VNode`. Type checkers see the decorated function itself, returning a `Node`, and check calls against its signature. |
| [`builtin`][wybthon.component.builtin] | Internal: marks a built-in that renders markup (`Show`, `For`, `Loading`, ...) so a compiled template builds it with getters for its dynamic arguments, as it does a component. |

#### Declaring props

- **Parameters are props** (`title: str`). Reading `title` returns the
  value and tracks it; in a template, `{title}` is dynamic, unlike
  other bare names. The parent may pass a value, an accessor, or a
  getter (what the compiler makes of `<{Card} title={user().name}>`);
  getters and accessors are unwrapped on read.
- **Defaults** are ordinary parameter defaults: `step: int = 1`. Use
  [`prop(default_factory=...)`][wybthon.prop] for a mutable default;
  the factory runs once per instance.
- **Callable parameters** (`Callable[...]` or `Accessor[...]`, alone or
  in a union with `None`) read as what the parent passed, never calling
  it, so callbacks and accessors you mean to keep arrive intact.
- **Children** arrive as a `children` parameter, annotated with
  [`Children`][wybthon.Children]: `children: Children = None`. Pass
  children as the content of a component tag in a template
  (`<{Card} title="Hi">...</{Card}>`), as the `children` keyword, or
  with item syntax (`Card(title="Hi")[...]`).
- **`**rest`** (any name, such as `**attrs: Any`) collects the props
  the component doesn't declare, as a reactive, read-only view that
  spreads onto an element (`<div {attrs}>`). `*args` isn't allowed.
- **Arguments bind as in a Python call**: `Greeting("Ada")` is
  `Greeting(name="Ada")`. Positional arguments are never children.
- **Parameters are read-only**: assigning to one, `del`, rebinding it
  with `for`, `import`, or `except`, or declaring it `nonlocal` is a
  `SyntaxError` when the module is compiled.
- A component with no inputs takes no parameters.

In dev mode, an unknown prop or a missing required one raises
`TypeError` at the call site, and so does calling a component with
parameters whose module wasn't compiled. [`merge`][wybthon.merge] and
[`omit`][wybthon.omit] combine or trim views (dicts, `**rest` views,
and other views) before you spread them: `merge({"type": "button"}, attrs)`.

```python
from collections.abc import Callable
from typing import Any

from wybthon import Children, component, create_signal, html, untrack


@component
def Counter(label: str = "Count", initial: int = 0, on_change: Callable[[int], None] | None = None):
    count, set_count = create_signal(untrack(lambda: initial))  # a one-time read

    def increment():
        set_count(lambda n: n + 1)
        if on_change is not None:
            on_change(count.peek() + 1)

    return html(t"""
      <div>
        <p>{label}: {count()}</p>
        <button onclick={increment}>+</button>
      </div>
    """)


@component
def Card(title: str, children: Children = None, **attrs: Any):
    return html(t'<div class="card" {attrs}><h2>{title}</h2>{children}</div>')


heading, set_heading = create_signal("Hello")

Counter(initial=5, label="Clicks", on_change=print)
html(t"<{Card} title={heading()} id='intro'><p>body text</p></{Card}>")  # title stays live
html(t"{Card(title=heading(), children=html(t'<p>body text</p>'))}")  # the same, type-checked
```

Reading a parameter or signal at the top level of the body reads it
once, as destructuring props does in Solid, and warns in dev mode when
the value was reactive; read it inside a template expression, memo, or
effect, or make the one-time read explicit with
[`untrack`][wybthon.untrack]. A prop the parent passed as a constant
can't change, so reading one doesn't warn.

Components don't take a `key`. To remount a component when an identity
changes, show it through a keyed `Show`:
`{Show(doc_id(), lambda current: DocumentView(doc_id=current), keyed=True)}`.

#### Using components in templates

Call a component inside an interpolation, `{Counter(initial=5)}`, to
keep full type checking of its props; the compiler still passes each
dynamic argument as a getter. The tag form,
`<{Card} title="Hi">...</{Card}>` or `<{Card} />`, passes attributes as
keyword props (a hyphen becomes an underscore) and nested markup as
`children`; type checkers can't see inside the template string, so
`wyb check` checks its props as the equivalent call, and dev mode
checks them at run time. See
[Templates](../concepts/templates.md#components-in-templates).

#### What a component costs

A component is only patched with new props when a reactive hole
re-renders a tree that contains it, or when `render` runs again into the
same container. Everywhere else (inside a template, another component's
output, a list row, or a `Show` branch) its props never change, so:

- reading a prop that the parent passed as a constant subscribes to
  nothing;
- a prop passed as a getter or accessor is read through, so the reader
  subscribes to that source directly;
- a binding that reads nothing reactive never allocates a computation.

A component whose props never change costs about what its markup costs.
Components that can be patched track one version signal per instance,
created on the first tracked read. Use [`is_static`][wybthon.is_static]
to ask whether the parent passed a plain value: `is_static(title)`,
passing the parameter itself, or `is_static(attrs, "key")` for a key of
a view.

A plain, undecorated function used as a tag, as in `h(fn, props)`,
receives the props dictionary and runs again when it's patched with
changed props. Use `@component` when you want typed, reactive props.

#### See also

- [Concepts: Components](../concepts/components.md)
- [Concepts: Templates](../concepts/templates.md)
- [Concepts: Compiler](../concepts/compiler.md)
- [Guides: Authoring patterns](../guides/authoring-patterns.md)
- [Guides: Typing](../guides/typing.md)
- [`Children`][wybthon.Children], [`prop`][wybthon.prop], [`merge`][wybthon.merge], [`omit`][wybthon.omit], [`is_static`][wybthon.is_static], [`resolve_children`][wybthon.resolve_children]
