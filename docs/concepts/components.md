# Components

Wybthon uses function components exclusively, following the SolidJS model.

!!! tip "Mental model"
    A component body **runs once** when it mounts and returns its
    markup, usually a [template](templates.md). Inputs are declared on
    a typed [`Props`][wybthon.Props] class, and reading `props.title`
    returns the parent's value, tracked, as reading a property of
    Solid's props object does. In the returned template, `{props.title}`
    is a dynamic expression, so the [compiler](compiler.md) makes it a
    binding and only that node updates when the value changes. See
    [Primitives](primitives.md#reactive-holes) for the full story.

## Declaring a component with `@component`

The [`component`][wybthon.component] decorator turns a function into a
[`Component`][wybthon.Component]. Declare inputs on a subclass of
[`Props`][wybthon.Props] as plain annotations, give defaults the way a
dataclass does, and take one parameter annotated with that class:

```python
from wybthon import Props, component, html, prop


class HelloProps(Props):
    name: str = "world"
    tags: list[str] = prop(default_factory=list)


@component
def Hello(props: HelloProps):
    return html(t"<p>Hello, {props.name}!</p>")
```

Reading a field returns its value, tracked:

- In the template, `{props.name}` is dynamic, so the compiler turns it into a getter: a binding that updates when the parent's value changes.
- In a memo or effect, `props.name` subscribes to the parent's value like any other tracked read.
- [`untrack(lambda: props.name)`][wybthon.untrack] reads it once without subscribing, for example to seed local state.

An ordinary default (`name: str = "world"`) needs nothing more. Use
[`prop(default_factory=...)`][wybthon.prop] for a mutable default; the
factory runs once per component instance. Type checkers only recognize
a field specifier's default when it's passed by keyword. `Props` is a
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
from wybthon import Props, component, create_signal, html, untrack


class CounterProps(Props):
    initial: int = 0


@component
def Counter(props: CounterProps):
    count, set_count = create_signal(untrack(lambda: props.initial))

    def increment():
        set_count(lambda n: n + 1)

    return html(t"""
      <div>
        <p>Count: {count()}</p>
        <button onclick={increment}>+1</button>
      </div>
    """)
```

The compiler turns `{count()}` into a getter, so the renderer gives
that slot one render effect and only that text node updates. The
surrounding body never runs again. Event handlers may take the event
or no arguments at all; prefer the zero-argument form when you don't
use the event.

### Values, expressions, and accessors

A child never has to care how the parent produced a prop. The parent
may pass a value, a template expression, or an accessor, and
`props.count` returns the current value in every case:

```python
from wybthon import Props, component, create_signal, html


class BadgeProps(Props):
    count: int


@component
def Badge(props: BadgeProps):
    return html(t"<span>count: {props.count}</span>")


n, set_n = create_signal(7)

Badge(count=7)  # a value
html(t"{Badge(count=n() * 2)}")  # an expression: the compiler passes a getter
html(t"<{Badge} count={n()} />")  # the same, in tag form
```

A dynamic expression in a component call or tag reaches the child as a
getter, the counterpart of the property getters Solid's compiler puts
on a props object, so the child's bindings follow `n` without the
parent re-running. Passing an accessor directly (`Badge(count=n)`)
works the same way at run time, but a type checker flags it against
`count: int`, so prefer writing the call in a template.

### Top-level reads warn

Reading a reactive prop or signal at the top level of the body isn't
tracked, so later updates never reach it. In dev mode Wybthon warns
once per component and value. A constant can't change, so reading one
doesn't warn:

```python
class NameProps(Props):
    name: str


@component
def Bad(props: NameProps):
    greeting = f"Hello, {props.name}"  # warns when name is reactive: frozen at mount
    return html(t"<p>{greeting}</p>")


@component
def Good(props: NameProps):
    return html(t"<p>Hello, {props.name}</p>")  # one reactive binding


@component
def AlsoFine(props: NameProps):
    initial = untrack(lambda: props.name)  # explicit one-time read, no warning
    return html(t"<p>{initial}</p>")
```

## Using a component

There are two ways to use a component in a template.

**The call form.** Calling a `Component` returns a
[`VNode`][wybthon.VNode]. Keyword arguments become props, and every
component also accepts `key=`. Call it inside an interpolation and the
type checker sees every prop, while the compiler still passes each
dynamic argument as a getter:

```python
html(t"""
  <main>
    {Counter(initial=5)}
    {Card(title=project().name, children=[html(t"<p>one</p>"), html(t"<p>two</p>")])}
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
else, including numbers, expressions, and callbacks, with `{...}`. A
dynamic value (`title={project().name}`) is passed as a getter. Type
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
props dictionary as it was passed, with no `Props` class, unwrapping, or
validation: a dynamic attribute arrives as a getter. It can't observe
later changes, so when a re-rendering hole patches it with changed
props, it's remounted and its body runs again. Use `@component` when
you want typed, reactive props.

```python
def Note(props):
    return html(t'<p class="note">{props["text"]}</p>')


html(t'<{Note} text="Saved" />')
```

### Passing callbacks

Annotate a callback field as callable. A field whose annotation is
`Callable[...]` or [`Accessor[...]`][wybthon.Accessor], alone or in a
union with `None`, returns exactly what the parent passed, and the read
never calls it:

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
unwrapped, so a zero-argument callback such as `on_close` is passed
through untouched. Every other field unwraps an accessor or getter on
read. Annotate a field as `Accessor[T]` when the child wants the
accessor itself rather than its value.

## What props cost

A component costs about what its markup costs. Whether a prop read
allocates anything depends on whether the component can ever receive
new props, which the renderer knows when it mounts the component:

- **Most components can't be patched.** A component mounted in another component's output, in a list row, in a `Show` branch, or anywhere else that's mounted once never receives new props. For these, reading a prop that the parent passed as a constant tracks nothing: there's no signal, no subscription, and nothing to dispose. A prop passed as an expression or an accessor is read through it, so the reader subscribes to that source directly.
- **A patchable component** is part of the tree a reactive hole returns, or of the tree passed to [`render`][wybthon.render], and not inside another component's output. When the hole re-runs (or you `render` into the same container again), the reconciler patches the component with the new props instead of remounting it. Its prop reads track one version signal per props instance, created on the first tracked read, and a patch that changes a prop bumps it.

The difference is only in what's allocated. Both kinds behave the same
for every prop passed as an expression or changed through a patch, so
you never need to think about which one you have.

Bindings get the same treatment. A binding whose expression makes no
calls, such as `{props.title}`, first runs under a lightweight probe:
when it reads nothing reactive, because the parent passed a constant,
the value is applied and no computation is ever allocated. Any other
binding or hole that reads nothing reactive on its first run is
dropped after that run, keeping only the DOM it produced.

### Checking for a static prop

[`is_static(props, "name")`][wybthon.is_static] reports whether the
parent passed a plain value rather than an expression, as Solid 2.0's
`isStatic` does. Nothing is read or tracked. A component library can
use it to take a cheaper path for a prop that can't change:

```python
@component
def Icon(props: IconProps):
    if is_static(props, "name"):
        return html(t"<i class={untrack(lambda: props.name)}></i>")
    return html(t"<i class={props.name}></i>")
```

## Forwarding with `merge` and `omit`

Every prop a component accepts is declared, and undeclared props can't
be read. To forward props onto an element, combine sources with
[`merge`][wybthon.merge] and drop the ones you handle yourself with
[`omit`][wybthon.omit]. Both return views that read like props
(`view.title` is the tracked value), and spreading a view onto an
element with `<tag {attrs}>` binds each key reactively:

```python
from wybthon import ParentProps, component, html, merge, omit


class ButtonProps(ParentProps):
    variant: str = "solid"
    disabled: bool = False


@component
def Button(props: ButtonProps):
    attrs = merge({"type": "button"}, omit(props, "variant", "children"))
    return html(t'<button {attrs} class="btn btn-{props.variant}">{props.children}</button>')
```

If the parent passes `disabled={is_busy()}`, the attribute follows the
signal. `omit` also accepts a predicate, such as
`omit(props, lambda key: key.startswith("on_"))`.

## Children

Subclass [`ParentProps`][wybthon.ParentProps] to accept children; it
declares `children: Any = None`. Most layouts interpolate
`props.children` where the content belongs:

```python
from wybthon import ParentProps, component, html


class CardProps(ParentProps):
    title: str


@component
def Card(props: CardProps):
    return html(t'<section class="card"><h3>{props.title}</h3>{props.children}</section>')


html(t'<{Card} title="Hi"><p>a</p><p>b</p></{Card}>')  # tag form
Card(title="Hi")[html(t"<p>a</p>"), html(t"<p>b</p>")]  # item syntax
Card(title="Hi", children=[html(t"<p>a</p>")])  # children as a keyword
```

When you need to inspect or iterate children, resolve them with
[`children`][wybthon.children]. It takes a getter for the children and
returns a [`ChildrenAccessor`][wybthon.ChildrenAccessor] that resolves
nested accessors, flattens lists, and drops `None` and booleans.
Calling it returns the single child or a list; `to_array()` always
returns a list. [`flatten`][wybthon.flatten] is the unmemoized form,
for a one-off resolution:

```python
from wybthon import ParentProps, children as resolve_children, component, html


@component
def List(props: ParentProps):
    kids = resolve_children(lambda: props.children)

    def items():
        return [html(t"<li>{kid}</li>") for kid in kids.to_array()]

    return html(t"<ul>{items()}</ul>")


List()["Apples", "Pears"]
```

## What a component may return

The body may return a template or any other `VNode`, a string, a list
(mounted as a fragment), `None` (renders nothing), or a reactive
expression (mounted as a single hole):

```python
class LabelProps(Props):
    text: str


@component
def Label(props: LabelProps):
    return create_memo(lambda: props.text.upper())  # a hole that tracks text
```

## Keys force a remount

The reconciler patches a component in place when a hole re-renders it
with the same tag and key: new props flow into the existing props
instance and the body doesn't run again. Give it a different `key` to
force a fresh instance with fresh local state:

```python
class EditorProps(Props):
    user_id: int


@component
def Editor(props: EditorProps):
    draft, set_draft = create_signal("")  # reset when the key changes

    def update(event):
        set_draft(event.target.value)

    return html(t"<textarea value={draft()} oninput={update}></textarea>")


def editor():
    return Editor(user_id=current_id(), key=current_id())


html(t"<div>{editor()}</div>")
```

`{editor()}` is a call with no arguments, so it's a reactive hole that
re-runs when `current_id` changes.

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
from wybthon import Portal, Props, Show, component, html


class ModalProps(Props):
    open: bool


@component
def Modal(props: ModalProps):
    return html(t"""
      {Show(props.open, Portal(html(t'<div class="modal"><p>Modal content</p></div>'), mount="#modal-root"))}
    """)
```

Writing the `Show` call in the template matters: there, `props.open`
is passed as a getter, while `Show(props.open, ...)` in the body would
read the prop once.

## Flow control

`Show`, `For`, `Repeat`, and `Switch` aren't components: they're native
regions the renderer mounts directly, with no component context or
props object of their own. Each one owns a scope, so only the relevant
subtree updates when a condition or list changes. Called in a template,
each dynamic argument arrives as a getter; `children` and `fallback`
slots are nodes or callables evaluated inside the region's scope.

```python
from wybthon import For, Match, Repeat, Show, Switch, html


def welcome(u):
    return html(t"<p>Welcome, {u().name}</p>")  # u is an accessor for the truthy value


def todo_row(todo, i):
    return html(t"<li>{todo.title}</li>")  # matched by identity: the raw item


def name_row(name, i):
    return html(t"<li>{name()}</li>")  # keyed=False: matched by position, name is an accessor


def keyed_row(todo, i):
    return html(t"<li>{todo().title}</li>")  # a key function: both are accessors


def star(i):
    return html(t"<span>*</span>")


loading = html(t"<p>Loading...</p>")
ready = html(t"<p>Ready</p>")
unknown = html(t"<p>Unknown</p>")

html(t"""
  {Show(user(), welcome, fallback=html(t"<p>Please log in</p>"))}
  <ul>{For(todos(), todo_row)}</ul>
  <ul>{For(names(), name_row, keyed=False)}</ul>
  <ul>{For(todos(), keyed_row, keyed=lambda t: t.id)}</ul>
  {Repeat(rating(), star)}
  {Switch(Match(status() == "loading", loading), Match(status() == "ready", ready), fallback=unknown)}
""")
```

The callbacks are typed. With a `todos: Accessor[list[Todo]]`, the
default `For` infers `todo: Todo` and `i: Accessor[int]`; `keyed=False`
gives `(Accessor[Todo], int)`, and a key function gives
`(Accessor[Todo], Accessor[int])`. `Show(user, lambda u: ...)` infers
`u: Accessor[User]`, or `u: User` with `keyed=True`.

[`dynamic`][wybthon.dynamic] picks a component or tag at run time:
`View = dynamic(lambda: views[mode()])`, then `{View(title="Hello")}`
in a template.

When a reactive hole re-renders a region of the same kind, the new
condition or source is pushed into the mounted region instead of
remounting it, so rows and branch state survive.

Outside a template, `For` needs an accessor for `each`
(`For(todos, todo_row)`); a plain list renders once and triggers a dev
warning. The full callback shapes are on the [`For`][wybthon.For] API
page and in [Primitives](primitives.md#map_array).

## Dev-mode diagnostics

With dev mode on (the default; check it with
[`is_dev_mode`][wybthon.is_dev_mode]), Wybthon reports the common
footguns:

- **Unknown or missing props**: calling a component with an undeclared prop, or without a required one, raises `TypeError`. This covers the tag form too.
- **Top-level reactive read** in a component body (warned once per component and value).
- **Write in a tracking scope**: writing a signal or store from a memo, a tracked effect, or a hole raises [`WriteInScopeError`][wybthon.WriteInScopeError].
- **Plain list in `For`**: the list renders once.
- **Uncompiled template**: a template that reached `html()` without the compiler, with a dynamic expression that was evaluated once, raises [`TemplateError`][wybthon.TemplateError]. See [Templates that weren't compiled](compiler.md#templates-that-werent-compiled).

Template markup errors aren't dev-only: markup the HTML parser would
rewrite is an error in every mode, reported when the module is
compiled. See [Templates](templates.md#markup-the-parser-would-rewrite-is-an-error).

Production builds made with `wyb build` turn dev mode off before your
application imports. Call [`set_dev_mode`][wybthon.set_dev_mode] to
change it yourself, for example in tests.

## Next steps

- Read [Templates](templates.md), [The compiler](compiler.md), [Mental model](mental-model.md), and [Lifecycle and ownership](lifecycle.md).
- Browse the [`component`][wybthon.component] and [`Props`][wybthon.Props] API references.
- See [Authoring patterns](../guides/authoring-patterns.md) for recipes.
