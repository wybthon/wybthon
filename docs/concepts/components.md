# Components

Wybthon uses function components exclusively, following the SolidJS model.

!!! tip "Mental model"
    A component body **runs once** when it mounts and returns its
    markup, usually a [template](templates.md). Its inputs are ordinary
    function parameters, and the [compiler](compiler.md) turns every
    read of a parameter into a tracked read of the parent's current
    value, as reading a property of Solid's props object is. In the
    returned template, `{title}` is a dynamic expression, so the
    compiler makes it a binding and only that node updates when the
    value changes. See [Primitives](primitives.md#reactive-holes) for
    the full story.

## Declaring a component with `@component`

The [`component`][wybthon.component] decorator turns a function into a
[`Component`][wybthon.Component]. The function's parameters are its
props: declare each input as a parameter with an annotation and, when
it's optional, a default:

```python
from wybthon import component, html, prop


@component
def Hello(name: str = "world", tags: list[str] = prop(default_factory=list)):
    return html(t"<p>Hello, {name}!</p>")
```

The compiler rewrites every read of a parameter inside an `@component`
body, so a parameter always reads as the parent's current value,
tracked:

- In the template, `{name}` is dynamic. Other bare names are applied once, but a parameter is a read of a prop, so the compiler turns it into a getter: a binding that updates when the parent's value changes.
- In a memo or effect, `name` subscribes to the parent's value like any other tracked read.
- In an event handler, `name` reads the latest value when the handler runs.
- [`untrack(lambda: name)`][wybthon.untrack] reads it once without subscribing, for example to seed local state.

An ordinary default (`name: str = "world"`) needs nothing more. Use
[`prop(default_factory=...)`][wybthon.prop] for a mutable default; the
factory runs once per component instance, so instances never share a
list.

A type checker sees an `@component` as the function itself, returning
a [`Node`][wybthon.Node], so pyright, Pylance, and mypy check every call
against the function's own signature with no plugin: a missing
required prop, a wrong type, or an unknown name is a type error that
names the component. Inside the body, a parameter has its annotated
type. See the [Typing guide](../guides/typing.md).

A component with no inputs takes no parameters:

```python
@component
def App():
    return html(t"<main>{Hello(name='Wybthon')}</main>")
```

### Parameters are read-only

A parameter is the parent's prop, so the body can't rebind it.
Assigning to a parameter, augmented assignment (`count += 1`), `del`,
rebinding it with `for`, `import`, or `except ... as`, and declaring it
`nonlocal` in a nested function are all compile-time errors:

```text
SyntaxError: 'title' is a component parameter, which is a read-only prop; assign to a new name
```

Give the value a new name instead (`label = title.upper()` reads it
once, as any top-level read does). A nested function, lambda,
comprehension, or class that binds the same name shadows the parameter,
as Python's scoping rules say, so `[title for title in titles]` is
fine.

A component can't take `*args`; declare a `children` parameter for its
content. A `**rest` parameter collects the props the component doesn't
declare (see [Forwarding with `**rest`](#forwarding-with-rest-merge-and-omit)).

### Components must be compiled

The compiler gives parameters their meaning, so a component's module
must be compiled, as a module with templates must be. The import hook
that `import wybthon` installs compiles every module imported after it,
and `wyb build`, `wyb dev`, `wyb run`, and Wybthon's pytest plugin
compile the modules they load. In dev mode, calling an uncompiled
component that has parameters raises `TypeError` with a message saying
the component wasn't compiled. See [Where it runs](compiler.md#where-it-runs).

## Bodies run once

There's no re-render. The only things that update later are the
bindings and holes in the returned markup and the effects created in
the body.

```python
from wybthon import component, create_signal, html, untrack


@component
def Counter(initial: int = 0):
    count, set_count = create_signal(untrack(lambda: initial))

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
may pass a value, a template expression, or an accessor, and `count`
reads as the current value in every case:

```python
from wybthon import component, create_signal, html


@component
def Badge(count: int):
    return html(t"<span>count: {count}</span>")


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

Reading a parameter at the top level of the body reads it once, as
destructuring props does in Solid: later updates never reach that
value. The same goes for a signal. In dev mode Wybthon warns once per
component and value. A constant can't change, so reading one doesn't
warn:

```python
@component
def Bad(name: str):
    greeting = f"Hello, {name}"  # warns when name is reactive: frozen at mount
    return html(t"<p>{greeting}</p>")


@component
def Good(name: str):
    return html(t"<p>Hello, {name}</p>")  # one reactive binding


@component
def AlsoFine(name: str):
    initial = untrack(lambda: name)  # explicit one-time read, no warning
    return html(t"<p>{initial}</p>")
```

## Using a component

There are two ways to use a component in a template.

**The call form.** Calling a `Component` returns a
[`VNode`][wybthon.vnode.VNode]. Arguments bind to parameters as in an
ordinary Python call: keyword arguments by name, and positional ones in
order, so `Greeting("Ada")` is `Greeting(name="Ada")`. Call it inside an
interpolation and the type checker sees every prop, while the compiler
still passes each dynamic argument as a getter:

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
props are long. Positional arguments are never children: content goes
to the `children` parameter.

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
(`user-id` is `user_id`). A handler attribute takes the Python spelling
of a callback parameter: `onclick={save}` is `on_click`. A quoted value is a string; pass anything
else, including numbers, expressions, and callbacks, with `{...}`. A
dynamic value (`title={project().name}`) is passed as a getter. Type
checkers can't see inside the template string, so on their own they
don't check the tag form's props; [`wyb check`](../guides/typing.md#checking-tag-props-with-wyb-check)
does, by checking each tag as the equivalent call, and dev mode checks
them at run time, like any component call.

In dev mode (the default), calling a component with an undeclared prop
or without a required one raises `TypeError` at the call:
`Counter(bogus=1)` fails immediately instead of silently rendering.
Statically, a type checker checks the call against the component's
signature, so the same mistakes show up in your editor.

The low-level [`h`][wybthon.vnode.h] form still works (`h(Counter, {"initial": 5})`).

### Plain functions as tags

A function without `@component` whose only parameter is the props can be
used as a tag too, with the tag form or `h(fn, props)`. It receives the
props dictionary as it was passed, with no unwrapping or validation: a
dynamic attribute arrives as a getter. It can't observe later changes,
so when a re-rendering hole patches it with changed props, it's
remounted and its body runs again. Use `@component` when you want
typed, reactive props.

```python
def Note(props):
    return html(t'<p class="note">{props["text"]}</p>')


html(t'<{Note} text="Saved" />')
```

### Passing callbacks

Annotate a callback parameter as callable. A parameter whose annotation
is `Callable[...]` or [`Accessor[...]`][wybthon.Accessor], alone or in a
union with `None`, reads as exactly what the parent passed, and the
read never calls it:

```python
from collections.abc import Callable

from wybthon import component, html


@component
def Picker(on_pick: Callable[[str], None], on_close: Callable[[], None] | None = None):
    def pick():
        on_pick("apple")
        if on_close is not None:
            on_close()

    return html(t"<button onclick={pick}>Pick</button>")


Picker(on_pick=print, on_close=lambda: print("closed"))
```

Reading a parameter never calls a function the parent passed: a
callback such as `on_close` comes back exactly as it was passed,
whatever its parameter is annotated. What a read does unwrap is an
expression: a getter the compiler made from markup
(`title={user().name}`), or an accessor the parent passed (a signal or
memo). A parameter annotated as callable, or as `Accessor[T]`, gets the
accessor itself rather than its value.

Outside markup, pass an accessor to make a prop reactive:
`Card(title=create_memo(lambda: user().name))`. A lambda is a value.

## What props cost

A component costs about what its markup costs. Whether a prop read
allocates anything depends on whether the component can ever receive
new props, which the renderer knows when it mounts the component:

- **Most components can't be patched.** A component mounted in another component's output, in a list row, in a `Show` branch, or anywhere else that's mounted once never receives new props. For these, reading a prop that the parent passed as a constant tracks nothing: there's no signal, no subscription, and nothing to dispose. A prop passed as an expression or an accessor is read through it, so the reader subscribes to that source directly.
- **A patchable component** is part of the tree a reactive hole returns, or of the tree passed to [`render`][wybthon.render], and not inside another component's output. When the hole re-runs (or you `render` into the same container again), the reconciler patches the component with the new props instead of remounting it. Its prop reads track one version signal per instance, created on the first tracked read, and a patch that changes a prop bumps it.

The difference is only in what's allocated. Both kinds behave the same
for every prop passed as an expression or changed through a patch, so
you never need to think about which one you have.

Bindings get the same treatment. A binding whose expression makes no
calls, such as `{title}`, first runs under a lightweight probe: when it
reads nothing reactive, because the parent passed a constant, the value
is applied and no computation is ever allocated. Any other binding or
hole that reads nothing reactive on its first run is dropped after that
run, keeping only the DOM it produced.

### Checking for a static prop

[`is_static(name)`][wybthon.is_static] reports whether the parent
passed a plain value rather than an expression, as Solid 2.0's
`isStatic` does. Pass the parameter itself: the compiler turns the call
into a question about the prop, not its value, so nothing is read or
tracked. A component library can use it to take a cheaper path for a
prop that can't change:

```python
from wybthon import component, html, is_static, untrack


@component
def Icon(name: str):
    if is_static(name):
        return html(t"<i class={untrack(lambda: name)}></i>")
    return html(t"<i class={name}></i>")
```

For a key of a `**rest`, `merge`, or `omit` view, pass the view and the
key: `is_static(attrs, "title")`.

## Forwarding with `**rest`, `merge`, and `omit`

A component accepts only the props it declares, unless it takes a
`**rest` parameter. A `**rest` parameter (any name, such as
`**attrs: Any`) collects the props the component doesn't declare as a
reactive, read-only view. Reading a key of the view (`attrs.title`)
returns the tracked value, and spreading the view onto an element with
`<tag {attrs}>` binds each key reactively:

```python
from typing import Any

from wybthon import Children, component, html, merge


@component
def Button(variant: str = "solid", children: Children = None, **attrs: Any):
    forwarded = merge({"type": "button"}, attrs)
    return html(t'<button {forwarded} class="btn btn-{variant}">{children}</button>')
```

[`merge`][wybthon.merge] combines sources (dicts, `**rest` views, and
other views) into one reactive view; later sources win. Here the parent
can override `type`, and every other prop it passes, such as
`disabled={is_busy()}`, lands on the `<button>` and follows the signal.
An event handler such as `on_click=save` is passed through as the
callable itself.

[`omit`][wybthon.omit] returns a view without some keys, for example to
handle one of the forwarded props yourself: `omit(attrs, "title")`. It
also accepts a predicate, such as
`omit(attrs, lambda key: key.startswith("on_"))`.

## Children

Declare a `children` parameter to accept children, annotated with
[`Children`][wybthon.Children] (an alias of `Any`, for documentation)
and defaulting to `None`. Most layouts interpolate `children` where the
content belongs:

```python
from wybthon import Children, component, html


@component
def Card(title: str, children: Children = None):
    return html(t'<section class="card"><h3>{title}</h3>{children}</section>')


html(t'<{Card} title="Hi"><p>a</p><p>b</p></{Card}>')  # tag form
Card(title="Hi")[html(t"<p>a</p>"), html(t"<p>b</p>")]  # item syntax
Card(title="Hi", children=[html(t"<p>a</p>")])  # children as a keyword
```

When you need to inspect or iterate children, resolve them with
[`resolve_children`][wybthon.resolve_children]. It takes a getter for the children and
returns a [`ChildrenAccessor`][wybthon.ChildrenAccessor] that resolves
nested accessors, flattens lists, and drops `None` and booleans.
Calling it returns the single child or a list; `to_array()` always
returns a list. [`flatten`][wybthon.flatten] is the unmemoized form,
for a one-off resolution:

```python
from wybthon import Children, component, html, resolve_children


@component
def List(children: Children = None):
    kids = resolve_children(lambda: children)

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
@component
def Label(text: str):
    return create_memo(lambda: text.upper())  # a hole that tracks text
```

## Remounting when an identity changes

A component stays mounted while the value it depends on changes: a
parameter reads the parent's current value, so `Editor` below keeps
its local state (the draft) when its `doc_id` changes. When a different identity
should get a fresh instance with fresh local state, show it through a
keyed [`Show`][wybthon.Show], as in Solid:

```python
from wybthon import Show, component, create_signal, html


@component
def Editor(doc_id: str):
    draft, set_draft = create_signal("")  # fresh for each document

    def update(event):
        set_draft(event.target.value)

    return html(t"<textarea value={draft()} oninput={update}></textarea>")


@component
def Workspace():
    doc_id, set_doc_id = create_signal("intro")
    return html(t"<div>{Show(doc_id(), lambda current: Editor(doc_id=current), keyed=True)}</div>")
```

With `keyed=True`, `Show` re-creates its branch every time the value
changes and hands the callback the raw value: the old `Editor` is
disposed (its cleanups run) and a new one mounts. Like any `Show`, it
renders nothing while the value is falsy. To render a list with one
instance per item, use [`For`](#flow-control). Components don't take a
`key`; [`h(tag, {"key": ...})`][wybthon.vnode.h] still keys any node,
as a low-level escape hatch.

## Refs through components

There's no `forward_ref`. Declare `ref` as an ordinary parameter and
pass it on; an element's `ref` takes a [`Ref`][wybthon.Ref], a callback,
or a list of either, so a component can forward the parent's ref and
keep its own:

```python
from wybthon import Ref, component, html, on_settled


@component
def FancyInput(ref: Ref | None = None):
    local = Ref()
    on_settled(lambda: local.current.element.focus())
    return html(t'<input type="text" class="fancy" ref={[local, ref]}>')
```

## Fragments

A template with several top-level nodes returns a fragment, so you
rarely need a wrapper element. The reconciler mounts a fragment's
children directly in the parent (between two empty comment markers, or,
when the fragment fills a slot by itself, in front of the slot's
placeholder), so fragments never disturb CSS selectors or layout.

```python
from wybthon import component, html


@component
def PageContent():
    return html(t"<h1>Title</h1><p>Body text here.</p>")
```

When you build the children in code, group them with
[`Fragment`][wybthon.vnode.Fragment]: `Fragment(*sections)`.

## Portal

[`Portal`][wybthon.Portal] mounts children into another DOM container
(an [`Element`][wybthon.Element], a CSS selector, or a kernel node id;
the default is `"body"`) while keeping them in the current ownership
tree, so context, signals, and cleanup work as usual:

```python
from wybthon import Portal, Show, component, html


@component
def Modal(open: bool):
    return html(t"""
      {Show(open, Portal(html(t'<div class="modal"><p>Modal content</p></div>'), mount="#modal-root"))}
    """)
```

Writing the `Show` call in the template matters: there, `open` is
passed as a getter, while `Show(open, ...)` in the body would read the
prop once. The `Portal` call is the branch's content, so the compiler
makes it lazy: the portal and its markup are built only when `open` is
truthy.

## Flow control

`Show`, `For`, `Repeat`, and `Switch` aren't components: they're native
regions the renderer mounts directly, with no component context or
props of their own. Each one owns a scope, so only the relevant
subtree updates when a condition or list changes. Called in a template,
each dynamic argument arrives as a getter; `children` and `fallback`
slots are nodes or callables evaluated inside the region's scope.

The compiler makes the content and fallback of `Show`, `Match`,
`Switch` (its fallback), `Loading`, `Errored`, and `client_only` lazy
when they're written as markup (`html(t"...")`) or as a component call
(a call whose callee name is capitalized, such as `Panel()`): each
becomes a zero-argument function, so a branch's markup and components
are built only when it shows, as JSX children are in Solid. A component
call in a branch still receives getters for its dynamic props. Names,
lambdas, and lowercase calls are passed as written.

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

- **Unknown or missing props**: calling a component with an undeclared prop (when it has no `**rest` parameter), or without a required one, raises `TypeError`. This covers the tag form too.
- **`key=` on a component**: components take no `key`, so passing one raises `TypeError` that points to a keyed `Show`.
- **Uncompiled component**: calling a component with parameters whose module wasn't compiled raises `TypeError`.
- **Top-level reactive read** in a component body (warned once per component and value).
- **Write in a tracking scope**: writing a signal or store from a memo, a tracked effect, or a hole raises [`WriteInScopeError`][wybthon.WriteInScopeError].
- **Plain list in `For`**: the list renders once.
- **Uncompiled template**: a template that reached `html()` without the compiler, with a dynamic expression that was evaluated once, raises [`TemplateError`][wybthon.TemplateError]. See [Templates that weren't compiled](compiler.md#templates-that-werent-compiled).

Template markup errors and writes to a parameter aren't dev-only: markup
the HTML parser would rewrite, and a body that rebinds a parameter, are
errors in every mode, reported when the module is compiled. See
[Templates](templates.md#markup-the-parser-would-rewrite-is-an-error).

Production builds made with `wyb build` turn dev mode off before your
application imports. Call [`set_dev_mode`][wybthon.set_dev_mode] to
change it yourself, for example in tests.

## Next steps

- Read [Templates](templates.md), [The compiler](compiler.md), [Mental model](mental-model.md), and [Lifecycle and ownership](lifecycle.md).
- Browse the [`component`][wybthon.component], [`Children`][wybthon.Children], and [`prop`][wybthon.prop] API references.
- See [Authoring patterns](../guides/authoring-patterns.md) for recipes.
