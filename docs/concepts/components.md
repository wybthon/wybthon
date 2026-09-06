# Components

Wybthon uses function components exclusively, following the SolidJS model.

!!! tip "Mental model"
    A component body **runs once** when it mounts. Every parameter is a
    [`Prop`][wybthon.Prop] accessor. Embed an accessor in the returned
    tree to create a *reactive hole*, so only that node updates when the
    value changes. See [Primitives](primitives.md#reactive-holes) for
    the full story.

## Declaring a component with `@component`

The [`component`][wybthon.component] decorator turns a function into a
[`Component`][wybthon.Component]. Declare props as ordinary parameters,
annotate them as `Prop[T]`, and give defaults with [`prop`][wybthon.prop]:

```python
from wybthon import Prop, component, prop
from wybthon.html import p


@component
def Hello(name: Prop[str] = prop("world")):
    return p("Hello, ", name, "!")
```

Each parameter is bound to a `Prop`:

- Place it in the tree (`p("Hello, ", name)`) for an automatic reactive hole.
- Call it (`name()`) inside a hole, memo, or effect to read the current value with tracking.
- Call `name.peek()` to read once without subscribing, for example to seed local state.

`prop(default)` exists so the parameter's type is `Prop[T]` rather than `T`.
A plain default (`name="world"`) works too when you don't care about the
type; the reconciler unwraps either into the same accessor.

## Bodies run once

There's no re-render. The only things that update later are the holes
embedded in the returned tree and the effects created in the body.

```python
from wybthon import Prop, component, create_signal, prop
from wybthon.html import button, div, p, span


@component
def Counter(initial: Prop[int] = prop(0)):
    count, set_count = create_signal(initial.peek())

    return div(
        p("Count: ", span(count)),
        button("+1", on_click=lambda e: set_count(lambda n: n + 1)),
    )
```

`count` is an accessor placed as a child, so the reconciler wraps it in
its own render effect; only that text node updates. The surrounding body
never runs again.

### Static or accessor, same call site

A child never has to care whether the parent passed a constant or a
signal; both are unwrapped uniformly:

```python
from wybthon import Prop, component, create_signal
from wybthon.html import span


@component
def Badge(count: Prop[int]):
    return span("count: ", count)


n, set_n = create_signal(7)

Badge(count=7)              # static value
Badge(count=n)              # signal accessor: updates when n changes
Badge(count=lambda: n() * 2)  # any zero-arg expression
```

### Top-level reads warn

Reading a prop or signal at the top level of the body isn't tracked, so
later updates never reach it. In dev mode Wybthon warns once per
component and value:

```python
@component
def Bad(name: Prop[str]):
    greeting = f"Hello, {name()}"   # warns: frozen at mount
    return p(greeting)


@component
def Good(name: Prop[str]):
    return p(lambda: f"Hello, {name()}")   # hole: tracked


@component
def AlsoFine(name: Prop[str]):
    initial = name.peek()   # explicit one-time read, no warning
    return p(initial)
```

## Calling a component

Calling a `Component` returns a [`VNode`][wybthon.VNode]. Keyword
arguments become props; positional arguments become the `children`
prop:

```python
Counter(initial=5)
Card("child1", "child2", title="My card")   # children=["child1", "child2"]
```

The low-level [`h`][wybthon.h] form still works (`h(Counter, {"initial": 5})`).

### Passing callbacks

A callback that takes arguments is passed through unchanged, and the
child calls the prop to get it:

```python
@component
def Picker(on_pick: Prop):
    return button("Pick", on_click=lambda e: on_pick()("apple"))


Picker(on_pick=lambda fruit: print(fruit))
```

Zero-argument callables are treated as reactive expressions and
unwrapped when the prop is read. To pass a zero-arg function *as a
value*, read it with `props.raw()` (below) instead.

## `**rest` and forwarding

Undeclared props arrive as `Prop`s in `**rest`. Spread them onto an
element, or combine them with [`merge`][wybthon.merge] and
[`omit`][wybthon.omit]:

```python
from typing import Any

from wybthon import Prop, component, merge, prop
from wybthon.html import button


@component
def Button(variant: Prop[str] = prop("solid"), **rest: Prop[Any]):
    attrs = merge({"type": "button"}, rest)
    return button(**attrs, class_=lambda: f"btn btn-{variant()}")
```

Because each forwarded value is an accessor, the element binds it
reactively: if the parent passes `disabled=is_busy`, the attribute
follows the signal.

## The `Props` mapping

A function with a single unannotated parameter named `props`, or a
parameter annotated [`Props`][wybthon.Props], receives the whole
mapping instead of individual accessors:

```python
from wybthon import Props, component
from wybthon.html import p


@component
def Dump(props: Props):
    return p(lambda: ", ".join(f"{k}={props[k]()!r}" for k in props))
```

- `props.name` and `props["name"]` both return the `Prop` for that key (created on first use).
- `props.raw("name")` returns the value exactly as the parent passed it, untracked and not unwrapped. Use it for callbacks, VNodes, and accessors you intend to hand on rather than read.
- Iteration and `len()` cover the keys the parent passed; `in` also reports declared defaults.
- `props.snapshot()` returns the current unwrapped values as a plain dict.

Any other single-parameter signature, such as `def Card(title: Prop[str])`,
is an ordinary prop. Prefer named parameters for application code;
reach for `Props` in generic wrappers.

## Children

`children` is a normal prop. Most layouts pass it straight through as a
child, which makes it a hole that re-renders when the parent supplies
new children:

```python
from typing import Any

from wybthon import Prop, component, prop
from wybthon.html import h3, section


@component
def Card(title: Prop[str], children: Prop[Any] = prop(None)):
    return section(h3(title), children, class_="card")
```

When you need to inspect or iterate children, resolve them with
[`children`][wybthon.children], which returns a memo yielding a flat
list with nested lists expanded and `None` dropped:

```python
from wybthon import children as resolve_children
from wybthon.html import li, ul


@component
def List(children: Prop[Any] = prop(None)):
    kids = resolve_children(children)
    return ul(lambda: [li(k) for k in kids()])
```

## What a component may return

The body may return a `VNode`, a string, a list (mounted as a
fragment), `None` (renders nothing), or a reactive expression (mounted
as a single hole):

```python
@component
def Label(text: Prop[str]):
    return create_memo(lambda: text().upper())   # a hole that tracks text
```

## Keys force a remount

The reconciler patches a component in place when a hole re-renders it
with the same tag and key: new props flow into the existing accessors
and the body doesn't run again. Give it a different `key` to force a
fresh instance with fresh local state:

```python
@component
def Editor(user_id: Prop[int]):
    draft, set_draft = create_signal("")   # reset when the key changes
    return textarea(value=draft, on_input=lambda e: set_draft(e.target.value))


div(lambda: Editor(user_id=current_id(), key=current_id()))
```

## Refs through components

There's no `forward_ref`. Accept `ref` like any prop and pass it on;
the `ref` prop takes a [`Ref`][wybthon.Ref], a callback, or a list of
either, so a component can forward the parent's ref and keep its own:

```python
from wybthon import Prop, Ref, component, on_settled, prop
from wybthon.html import input_


@component
def FancyInput(ref: Prop[Ref | None] = prop(None)):
    local = Ref()
    on_settled(lambda: local.current.element.focus())
    return input_(type="text", class_="fancy", ref=[local, ref.peek()])
```

## Fragment

Use [`Fragment`][wybthon.Fragment] to group children without a wrapper
element. The reconciler mounts the children directly in the parent
between two empty comment markers, so fragments never disturb CSS
selectors or layout.

```python
from wybthon import Fragment, component
from wybthon.html import h1, p


@component
def PageContent():
    return Fragment(h1("Title"), p("Body text here."))
```

## Portal

[`Portal`][wybthon.Portal] mounts children into another DOM container
(an [`Element`][wybthon.Element], a CSS selector, or a kernel node id;
the default is `"body"`) while keeping them in the current ownership
tree, so context, signals, and cleanup work as usual:

```python
from wybthon import Portal, Show, component
from wybthon.html import div, p


@component
def Modal(open: Prop[bool]):
    return Show(open, lambda: Portal(div(p("Modal content"), class_="modal"), mount="#modal-root"))
```

## Flow control

Wybthon provides reactive flow-control components. Each creates its own
scope, so only the relevant subtree updates when a condition or list
changes. Conditions and sources are accessors; `children` and
`fallback` slots are VNodes or callables evaluated inside the
primitive's scope.

```python
from wybthon import Dynamic, For, Match, Repeat, Show, Switch
from wybthon.html import li, p, span

# Conditional: only truthiness is tracked; the callback receives an accessor.
Show(user, lambda u: p("Welcome, ", lambda: u()["name"]), fallback=p("Please log in"))

# Lists: rows match by identity (default), by position, or by key.
For(todos, lambda todo, i: li(todo["title"]))
For(names, lambda name, i: li(name), keyed=False)          # name is an accessor
For(todos, lambda todo, i: li(lambda: todo()["title"]), keyed=lambda t: t["id"])

# Count-driven rendering with no diffing.
Repeat(rating, lambda i: span("*"))

# Multi-branch matching.
Switch(
    Match(lambda: status() == "loading", lambda: p("Loading...")),
    Match(lambda: status() == "ready", lambda: p("Ready")),
    fallback=lambda: p("Unknown"),
)

# A component or tag chosen at runtime.
Dynamic(lambda: views[mode()], title="Hello")
```

`For` needs an accessor for `each`; a plain list renders once and
triggers a dev warning. The full callback shapes are on the
[`For`][wybthon.For] API page and in [Primitives](primitives.md#map_array).

## Dev-mode diagnostics

With [`DEV_MODE`][wybthon.DEV_MODE] on (the default), Wybthon reports the
common footguns:

- **Top-level reactive read** in a component body (warned once per component and value).
- **Write in a tracking scope**: writing a signal or store from a memo, a single-function effect, or a hole raises [`WriteInScopeError`][wybthon.WriteInScopeError].
- **Plain list in `For`**: the list renders once.

Call [`set_dev_mode(False)`][wybthon.set_dev_mode] in production builds.

## Next steps

- Read [Mental model](mental-model.md) and [Lifecycle and ownership](lifecycle.md).
- Browse the [`component`][wybthon.component] and [`props`](../api/props.md) API references.
- See [Authoring patterns](../guides/authoring-patterns.md) for recipes.
