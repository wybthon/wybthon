# Components

Wybthon uses function components exclusively, following the SolidJS model.

!!! tip "Mental model"
    A component body **runs once** when it mounts and returns its
    markup, usually a [template](templates.md). Inputs are declared on
    a typed [`Props`][wybthon.Props] class, and each
    [`Prop`][wybthon.Prop] field reads as an accessor. Interpolate an
    accessor in the returned template to create a reactive binding, so
    only that node updates when the value changes. See
    [Primitives](primitives.md#reactive-holes) for the full story.

## Declaring a component with `@component`

The [`component`][wybthon.component] decorator turns a function into a
[`Component`][wybthon.Component]. Declare inputs on a subclass of
[`Props`][wybthon.Props], annotate reactive fields as `Prop[T]`, give
defaults with [`prop`][wybthon.prop], and take one parameter annotated
with that class:

```python
from wybthon import Prop, Props, component, html, prop


class HelloProps(Props):
    name: Prop[str] = prop(default="world")


@component
def Hello(props: HelloProps):
    return html(t"<p>Hello, {props.name}!</p>")
```

Reading a `Prop[T]` field returns an [`Accessor`][wybthon.Accessor]:

- Interpolate it (`{props.name}`) for an automatic reactive binding.
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
    return html(t"<main>{Hello(name='Wybthon')}</main>")
```

## Bodies run once

There's no re-render. The only things that update later are the
bindings and holes in the returned markup and the effects created in
the body.

```python
from wybthon import Prop, Props, component, create_signal, html, prop


class CounterProps(Props):
    initial: Prop[int] = prop(default=0)


@component
def Counter(props: CounterProps):
    count, set_count = create_signal(props.initial.peek())

    def increment():
        set_count(lambda n: n + 1)

    return html(t"""
      <div>
        <p>Count: {count}</p>
        <button onclick={increment}>+1</button>
      </div>
    """)
```

The template interpolates an accessor, so the reconciler wraps that
slot in one render effect; only that text node updates. The surrounding
body never runs again. Event handlers may take the event or no
arguments at all; prefer the zero-argument form when you don't use the
event.

### Static or accessor, same call site

A child never has to care whether the parent passed a constant or a
signal; both are unwrapped uniformly:

```python
from wybthon import Prop, Props, component, create_signal, html


class BadgeProps(Props):
    count: Prop[int]


@component
def Badge(props: BadgeProps):
    return html(t"<span>count: {props.count}</span>")


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
    return html(t"<p>{greeting}</p>")


@component
def Good(props: NameProps):
    return html(t"<p>Hello, {props.name}</p>")  # one reactive binding


@component
def AlsoFine(props: NameProps):
    initial = props.name.peek()  # explicit one-time read, no warning
    return html(t"<p>{initial}</p>")
```

## Using a component

There are two ways to use a component in a template.

**The call form.** Calling a `Component` returns a
[`VNode`][wybthon.VNode]. Keyword arguments become props, and every
component also accepts `key=`. Call it inside an interpolation and the
type checker sees every prop:

```python
html(t"""
  <main>
    {Counter(initial=5)}
    {Card(title="My card", children=[html(t"<p>one</p>"), html(t"<p>two</p>")])}
    {Card(title="My card")[html(t"<p>one</p>"), html(t"<p>two</p>")]}
  </main>
""")
```

The last line uses item syntax for children, which reads well when the
props are long.

**The tag form.** `<{Card} ...>` reads like the rest of the markup and
passes the nested markup as the `children` prop. Close it with
`</{Card}>`, or self-close it with `<{Card} />`:

```python
html(t"""
  <{Card} title="Settings">
    <p>Changes apply immediately.</p>
    <{Counter} initial={5} />
  </{Card}>
""")
```

Attributes become keyword props, and a hyphen becomes an underscore
(`user-id` is `user_id`). A quoted value is a string; pass anything
else, including numbers, accessors, and callbacks, with `{...}`. Type
checkers can't see inside the template string, so the tag form's props
are checked at run time in dev mode, like any component call. Use the
call form when you want the checker's help.

In dev mode (the default), calling a component with an undeclared prop
or without a required one raises `TypeError` at the call:
`Counter(bogus=1)` fails immediately instead of silently rendering.
Statically, a type checker sees the call as constructing the props
class, so the same mistakes show up in your editor.

The low-level [`h`][wybthon.h] form still works (`h(Counter, {"initial": 5})`).

### Plain functions as tags

A function without `@component` whose only parameter is the props can be
used as a tag too, with the tag form or `h(fn, props)`. It receives the
props dictionary as it was passed, with no `Props` class, accessors, or
validation. It can't
observe later changes, so when a re-rendering hole patches it with
changed props, it's remounted and its body runs again. Use
`@component` when you want typed, reactive props.

```python
def Note(props):
    return html(t'<p class="note">{props["text"]}</p>')


html(t'<{Note} text="Saved" />')
```

### Passing callbacks

Declare callbacks as plain fields, annotated with anything other than
`Prop[...]`. A plain field returns exactly what the parent passed,
untracked, and the read never calls it:

```python
from collections.abc import Callable

from wybthon import Props, component, html


class PickerProps(Props):
    on_pick: Callable[[str], None]
    on_close: Callable[[], None] | None = None


@component
def Picker(props: PickerProps):
    def pick():
        props.on_pick("apple")
        if props.on_close is not None:
            props.on_close()

    return html(t"<button onclick={pick}>Pick</button>")


Picker(on_pick=print, on_close=lambda: print("closed"))
```

The declared type, not the callback's argument count, decides what's
reactive, so a zero-argument callback such as `on_close` is passed
through untouched. Plain fields use ordinary defaults (`= None`), not
`prop()`.

## What props cost

A component costs about what its markup costs. Whether a prop read
allocates anything depends on whether the component can ever receive
new props, which the renderer knows when it mounts the component:

- **Most components can't be patched.** A component mounted in another component's output, in a list row, in a `Show` branch, or anywhere else that's mounted once never receives new props. For these, reading a `Prop` field that the parent passed as a constant tracks nothing: there's no signal, no subscription, and nothing to dispose. A prop passed as an accessor or a zero-argument function is still called, so the reader subscribes to that source directly.
- **A patchable component** is part of the tree a reactive hole returns, or of the tree passed to [`render`][wybthon.render], and not inside another component's output. When the hole re-runs (or you `render` into the same container again), the reconciler patches the component with the new props instead of remounting it. Its `Prop` reads track one version signal per props instance, created on the first tracked read, and a patch that changes any reactive field bumps it.

The difference is only in what's allocated. Both kinds behave the same
for every prop passed as an accessor or changed through a patch, so you
never need to think about which one you have.

Bindings get the same treatment: a binding or hole that reads nothing
reactive on its first run (because every value it touched was a
constant) can never run again, so the renderer drops it and keeps only
the DOM it produced.

## Forwarding with `merge` and `omit`

Every prop a component accepts is declared, and undeclared props can't
be read. To forward props onto an element, combine sources with
[`merge`][wybthon.merge] and drop the ones you handle yourself with
[`omit`][wybthon.omit]. Both return a reactive mapping of accessors you
can spread onto an element with `<tag {attrs}>`:

```python
from wybthon import ParentProps, Prop, component, html, merge, omit, prop


class ButtonProps(ParentProps):
    variant: Prop[str] = prop(default="solid")
    disabled: Prop[bool] = prop(default=False)


@component
def Button(props: ButtonProps):
    attrs = merge({"type": "button"}, omit(props, "variant", "children"))
    return html(t'<button {attrs} class="btn btn-{props.variant}">{props.children}</button>')
```

Because each forwarded value is an accessor, the element binds it
reactively: if the parent passes `disabled=is_busy`, the attribute
follows the signal. `omit` also accepts a predicate, such as
`omit(props, lambda key: key.startswith("on_"))`.

## Children

Subclass [`ParentProps`][wybthon.ParentProps] to accept children; it
declares `children: Prop[Any]`. Most layouts interpolate
`props.children` where the content belongs:

```python
from wybthon import ParentProps, Prop, component, html


class CardProps(ParentProps):
    title: Prop[str]


@component
def Card(props: CardProps):
    return html(t'<section class="card"><h3>{props.title}</h3>{props.children}</section>')


html(t'<{Card} title="Hi"><p>a</p><p>b</p></{Card}>')  # tag form
Card(title="Hi")[html(t"<p>a</p>"), html(t"<p>b</p>")]  # item syntax
Card(title="Hi", children=[html(t"<p>a</p>")])  # children as a keyword
```

When you need to inspect or iterate children, resolve them with
[`children`][wybthon.children]. It returns a
[`ChildrenAccessor`][wybthon.ChildrenAccessor] that resolves nested
accessors, flattens lists, and drops `None` and booleans. Calling it
returns the single child or a list; `to_array()` always returns a list:

```python
from wybthon import ParentProps, children as resolve_children, component, html


@component
def List(props: ParentProps):
    kids = resolve_children(props.children)

    def items():
        return [html(t"<li>{kid}</li>") for kid in kids.to_array()]

    return html(t"<ul>{items}</ul>")


List()["Apples", "Pears"]
```

## What a component may return

The body may return a template or any other `VNode`, a string, a list
(mounted as a fragment), `None` (renders nothing), or a reactive
expression (mounted as a single hole):

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

    def update(event):
        set_draft(event.target.value)

    return html(t"<textarea value={draft} oninput={update}></textarea>")


def editor():
    return Editor(user_id=current_id(), key=current_id())


html(t"<div>{editor}</div>")
```

## Refs through components

There's no `forward_ref`. Declare `ref` as a plain field and pass it
on; an element's `ref` takes a [`Ref`][wybthon.Ref], a callback, or a
list of either, so a component can forward the parent's ref and keep
its own:

```python
from wybthon import Props, Ref, component, html, on_settled


class FancyInputProps(Props):
    ref: Ref | None = None


@component
def FancyInput(props: FancyInputProps):
    local = Ref()
    on_settled(lambda: local.current.element.focus())
    return html(t'<input type="text" class="fancy" ref={[local, props.ref]}>')
```

## Fragments

A template with several top-level nodes returns a fragment, so you
rarely need a wrapper element. The reconciler mounts a fragment's
children directly in the parent between two empty comment markers, so
fragments never disturb CSS selectors or layout.

```python
from wybthon import component, html


@component
def PageContent():
    return html(t"<h1>Title</h1><p>Body text here.</p>")
```

When you build the children in code, group them with
[`Fragment`][wybthon.Fragment]: `Fragment(*sections)`.

## Portal

[`Portal`][wybthon.Portal] mounts children into another DOM container
(an [`Element`][wybthon.Element], a CSS selector, or a kernel node id;
the default is `"body"`) while keeping them in the current ownership
tree, so context, signals, and cleanup work as usual:

```python
from wybthon import Portal, Prop, Props, Show, component, html


class ModalProps(Props):
    open: Prop[bool]


@component
def Modal(props: ModalProps):
    return Show(props.open, Portal(html(t'<div class="modal"><p>Modal content</p></div>'), mount="#modal-root"))
```

## Flow control

`Show`, `For`, `Repeat`, and `Switch` aren't components: they're native
regions the renderer mounts directly, with no component context or
props object of their own. Each one owns a scope, so only the relevant
subtree updates when a condition or list changes. Conditions and
sources are accessors; `children` and `fallback` slots are nodes or
callables evaluated inside the region's scope.

```python
from wybthon import For, Match, Repeat, Show, Switch, dynamic, html

# Conditional: only truthiness is tracked; the callback receives an accessor.
Show(user, lambda u: html(t"<p>Welcome, {(lambda: u().name)}</p>"), fallback=html(t"<p>Please log in</p>"))

# Lists: rows match by identity (default), by position, or by key.
For(todos, lambda todo, i: html(t"<li>{todo.title}</li>"))
For(names, lambda name, i: html(t"<li>{name}</li>"), keyed=False)  # name is an accessor
For(todos, lambda todo, i: html(t"<li>{(lambda: todo().title)}</li>"), keyed=lambda t: t.id)

# Count-driven rendering with no diffing.
Repeat(rating, lambda i: html(t"<span>*</span>"))

# Multi-branch matching.
Switch(
    Match(lambda: status() == "loading", html(t"<p>Loading...</p>")),
    Match(lambda: status() == "ready", html(t"<p>Ready</p>")),
    fallback=html(t"<p>Unknown</p>"),
)

# A component or tag chosen at runtime.
dynamic(lambda: views[mode()])(title="Hello")
```

The callbacks are typed. With a `todos: Accessor[list[Todo]]`, the
default `For` infers `todo: Todo` and `i: Accessor[int]`; `keyed=False`
gives `(Accessor[Todo], int)`, and a key function gives
`(Accessor[Todo], Accessor[int])`. `Show(user, lambda u: ...)` infers
`u: Accessor[User]`, or `u: User` with `keyed=True`.

When a reactive hole re-renders a region of the same kind, the new
condition or source is pushed into the mounted region instead of
remounting it, so rows and branch state survive.

`For` needs an accessor for `each`; a plain list renders once and
triggers a dev warning. The full callback shapes are on the
[`For`][wybthon.For] API page and in [Primitives](primitives.md#map_array).

## Dev-mode diagnostics

With dev mode on (the default; check it with
[`is_dev_mode`][wybthon.is_dev_mode]), Wybthon reports the common
footguns:

- **Unknown or missing props**: calling a component with an undeclared prop, or without a required one, raises `TypeError`. This covers the tag form too.
- **Top-level reactive read** in a component body (warned once per component and value).
- **Write in a tracking scope**: writing a signal or store from a memo, a tracked effect, or a hole raises [`WriteInScopeError`][wybthon.WriteInScopeError].
- **Plain list in `For`**: the list renders once.

Template markup errors aren't dev-only: markup the HTML parser would
rewrite raises [`TemplateError`][wybthon.TemplateError] the first time
the template is used, in every mode. See [Templates](templates.md#markup-the-parser-would-rewrite-is-an-error).

Production builds made with `wyb build` turn dev mode off before your
application imports. Call [`set_dev_mode`][wybthon.set_dev_mode] to
change it yourself, for example in tests.

## Next steps

- Read [Templates](templates.md), [Mental model](mental-model.md), and [Lifecycle and ownership](lifecycle.md).
- Browse the [`component`][wybthon.component] and [`Props`][wybthon.Props] API references.
- See [Authoring patterns](../guides/authoring-patterns.md) for recipes.
