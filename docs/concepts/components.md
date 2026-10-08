# Components

Wybthon uses function components exclusively, following the SolidJS model.

!!! tip "Mental model"
    A component body **runs once** when it mounts. Inputs are declared on
    a typed [`Props`][wybthon.Props] class, and each
    [`Prop`][wybthon.Prop] field reads as an accessor. Embed an accessor
    in the returned tree to create a *reactive hole*, so only that node
    updates when the value changes. See
    [Primitives](primitives.md#reactive-holes) for the full story.

## Declaring a component with `@component`

The [`component`][wybthon.component] decorator turns a function into a
[`Component`][wybthon.Component]. Declare inputs on a subclass of
[`Props`][wybthon.Props], annotate reactive fields as `Prop[T]`, give
defaults with [`prop`][wybthon.prop], and take one parameter annotated
with that class:

```python
from wybthon import Prop, Props, component, prop
from wybthon.html import p


class HelloProps(Props):
    name: Prop[str] = prop(default="world")


@component
def Hello(props: HelloProps):
    return p("Hello, ", props.name, "!")
```

Reading a `Prop[T]` field returns an [`Accessor`][wybthon.Accessor]:

- Place it in the tree (`p("Hello, ", props.name)`) for an automatic reactive hole.
- Call it (`props.name()`) inside a hole, memo, or effect to read the current value with tracking.
- Call `props.name.peek()` to read once without subscribing, for example to seed local state.

Pass defaults by keyword: `prop(default=...)`, or
`prop(default_factory=list)` for a mutable default. Type checkers only
recognize a field default when it's passed by keyword. `Props` is a
[PEP 681](https://peps.python.org/pep-0681/) `dataclass_transform`
base, so pyright and mypy check every call site with no plugin: a
missing required prop, a wrong type, or an unknown name is a type
error.

A component with no inputs takes no parameters:

```python
@component
def App():
    return Hello(name="Wybthon")
```

## Bodies run once

There's no re-render. The only things that update later are the holes
embedded in the returned tree and the effects created in the body.

```python
from wybthon import Prop, Props, component, create_signal, prop
from wybthon.html import button, div, p


class CounterProps(Props):
    initial: Prop[int] = prop(default=0)


@component
def Counter(props: CounterProps):
    count, set_count = create_signal(props.initial.peek())

    return div(
        p(t"Count: {count}"),
        button("+1", on_click=lambda: set_count(lambda n: n + 1)),
    )
```

The template string interpolates an accessor, so the reconciler wraps it
in one render effect; only that text node updates. The surrounding body
never runs again. Event handlers may take the event or no arguments at
all; prefer the zero-argument form when you don't use the event.

### Static or accessor, same call site

A child never has to care whether the parent passed a constant or a
signal; both are unwrapped uniformly:

```python
from wybthon import Prop, Props, component, create_signal
from wybthon.html import span


class BadgeProps(Props):
    count: Prop[int]


@component
def Badge(props: BadgeProps):
    return span("count: ", props.count)


n, set_n = create_signal(7)

Badge(count=7)  # static value
Badge(count=n)  # signal accessor: updates when n changes
Badge(count=lambda: n() * 2)  # any zero-arg expression
```

### Top-level reads warn

Reading a prop or signal at the top level of the body isn't tracked, so
later updates never reach it. In dev mode Wybthon warns once per
component and value:

```python
class NameProps(Props):
    name: Prop[str]


@component
def Bad(props: NameProps):
    greeting = f"Hello, {props.name()}"  # warns: frozen at mount
    return p(greeting)


@component
def Good(props: NameProps):
    return p(t"Hello, {props.name}")  # one reactive binding


@component
def AlsoFine(props: NameProps):
    initial = props.name.peek()  # explicit one-time read, no warning
    return p(initial)
```

## Calling a component

Calling a `Component` returns a [`VNode`][wybthon.VNode]. Keyword
arguments become props, and every component also accepts `key=`:

```python
Counter(initial=5)
Card(title="My card", children=[p("one"), p("two")])
Card(title="My card")[p("one"), p("two")]  # item syntax for children
```

In dev mode (the default), calling a component with an undeclared prop
or without a required one raises `TypeError` at the call:
`Counter(bogus=1)` fails immediately instead of silently rendering.
Statically, a type checker sees the call as constructing the props
class, so the same mistakes show up in your editor.

The low-level [`h`][wybthon.h] form still works (`h(Counter, {"initial": 5})`).

### Passing callbacks

Declare callbacks as plain fields, annotated with anything other than
`Prop[...]`. A plain field returns exactly what the parent passed,
untracked, and the read never calls it:

```python
from collections.abc import Callable

from wybthon import Props, component
from wybthon.html import button


class PickerProps(Props):
    on_pick: Callable[[str], None]
    on_close: Callable[[], None] | None = None


@component
def Picker(props: PickerProps):
    def pick():
        props.on_pick("apple")
        if props.on_close is not None:
            props.on_close()

    return button("Pick", on_click=pick)


Picker(on_pick=lambda fruit: print(fruit), on_close=lambda: print("closed"))
```

The declared type, not the callback's argument count, decides what's
reactive, so a zero-argument callback such as `on_close` is passed
through untouched. Plain fields use ordinary defaults (`= None`), not
`prop()`.

## Forwarding with `merge` and `omit`

Every prop a component accepts is declared, and undeclared props can't
be read. To forward props onto an element, combine sources with
[`merge`][wybthon.merge] and drop the ones you handle yourself with
[`omit`][wybthon.omit]. Both return a reactive mapping of accessors you
can spread:

```python
from wybthon import ParentProps, Prop, component, merge, omit, prop
from wybthon.html import button


class ButtonProps(ParentProps):
    variant: Prop[str] = prop(default="solid")
    disabled: Prop[bool] = prop(default=False)


@component
def Button(props: ButtonProps):
    attrs = merge({"type": "button"}, omit(props, "variant", "children"))
    return button(**attrs, class_=t"btn btn-{props.variant}")[props.children]
```

Because each forwarded value is an accessor, the element binds it
reactively: if the parent passes `disabled=is_busy`, the attribute
follows the signal. `omit` also accepts a predicate, such as
`omit(props, lambda key: key.startswith("on_"))`.

## Children

Subclass [`ParentProps`][wybthon.ParentProps] to accept children; it
declares `children: Prop[Any]`. Most layouts pass `props.children`
straight through, which makes it a hole that re-renders when the parent
supplies new children:

```python
from wybthon import ParentProps, Prop, component
from wybthon.html import h3, p, section


class CardProps(ParentProps):
    title: Prop[str]


@component
def Card(props: CardProps):
    return section(h3(props.title), props.children, class_="card")


Card(title="Hi", children=[p("a"), p("b")])  # children as a keyword
Card(title="Hi")[p("a"), p("b")]  # item syntax
```

Item syntax works on elements too: `section(class_="card")[h3("Hi")]`.

When you need to inspect or iterate children, resolve them with
[`children`][wybthon.children]. It returns a
[`ChildrenAccessor`][wybthon.ChildrenAccessor] that resolves nested
accessors, flattens lists, and drops `None` and booleans. Calling it
returns the single child or a list; `to_array()` always returns a list:

```python
from wybthon import ParentProps, children as resolve_children, component
from wybthon.html import li, ul


@component
def List(props: ParentProps):
    kids = resolve_children(props.children)
    return ul(lambda: [li(k) for k in kids.to_array()])
```

## What a component may return

The body may return a `VNode`, a string, a list (mounted as a
fragment), `None` (renders nothing), or a reactive expression (mounted
as a single hole):

```python
class LabelProps(Props):
    text: Prop[str]


@component
def Label(props: LabelProps):
    return create_memo(lambda: props.text().upper())  # a hole that tracks text
```

## Keys force a remount

The reconciler patches a component in place when a hole re-renders it
with the same tag and key: new props flow into the existing accessors
and the body doesn't run again. Give it a different `key` to force a
fresh instance with fresh local state:

```python
class EditorProps(Props):
    user_id: Prop[int]


@component
def Editor(props: EditorProps):
    draft, set_draft = create_signal("")  # reset when the key changes
    return textarea(value=draft, on_input=lambda e: set_draft(e.target.value))


div(lambda: Editor(user_id=current_id(), key=current_id()))
```

## Refs through components

There's no `forward_ref`. Declare `ref` as a plain field and pass it
on; an element's `ref` takes a [`Ref`][wybthon.Ref], a callback, or a
list of either, so a component can forward the parent's ref and keep
its own:

```python
from wybthon import Props, Ref, component, on_settled
from wybthon.html import input_


class FancyInputProps(Props):
    ref: Ref | None = None


@component
def FancyInput(props: FancyInputProps):
    local = Ref()
    on_settled(lambda: local.current.element.focus())
    return input_(type="text", class_="fancy", ref=[local, props.ref])
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
from wybthon import Portal, Prop, Props, Show, component
from wybthon.html import div, p


class ModalProps(Props):
    open: Prop[bool]


@component
def Modal(props: ModalProps):
    return Show(props.open, lambda: Portal(div(p("Modal content"), class_="modal"), mount="#modal-root"))
```

## Flow control

Wybthon provides reactive flow-control components. Each creates its own
scope, so only the relevant subtree updates when a condition or list
changes. Conditions and sources are accessors; `children` and
`fallback` slots are VNodes or callables evaluated inside the
primitive's scope.

```python
from wybthon import For, Match, Repeat, Show, Switch, dynamic
from wybthon.html import li, p, span

# Conditional: only truthiness is tracked; the callback receives an accessor.
Show(user, lambda u: p("Welcome, ", lambda: u()["name"]), fallback=p("Please log in"))

# Lists: rows match by identity (default), by position, or by key.
For(todos, lambda todo, i: li(todo["title"]))
For(names, lambda name, i: li(name), keyed=False)  # name is an accessor
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
dynamic(lambda: views[mode()])(title="Hello")
```

`For` needs an accessor for `each`; a plain list renders once and
triggers a dev warning. The full callback shapes are on the
[`For`][wybthon.For] API page and in [Primitives](primitives.md#map_array).

## Dev-mode diagnostics

With dev mode on (the default; check it with
[`is_dev_mode`][wybthon.is_dev_mode]), Wybthon reports the common
footguns:

- **Unknown or missing props**: calling a component with an undeclared prop, or without a required one, raises `TypeError`.
- **Top-level reactive read** in a component body (warned once per component and value).
- **Write in a tracking scope**: writing a signal or store from a memo, a tracked effect, or a hole raises [`WriteInScopeError`][wybthon.WriteInScopeError].
- **Plain list in `For`**: the list renders once.

Production builds made with `wyb build` turn dev mode off before your
application imports. Call [`set_dev_mode`][wybthon.set_dev_mode] to
change it yourself, for example in tests.

## Next steps

- Read [Mental model](mental-model.md) and [Lifecycle and ownership](lifecycle.md).
- Browse the [`component`][wybthon.component] and [`Props`][wybthon.Props] API references.
- See [Authoring patterns](../guides/authoring-patterns.md) for recipes.
