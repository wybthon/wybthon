# Authoring patterns

This guide shows how to author components in Wybthon's run-once model, with recipes for the situations that come up in every app.

!!! tip "Mental model in one line"
    Components run **once**. Inputs are declared on a [`Props`][wybthon.Props] class, and reading a [`Prop[T]`][wybthon.Prop] field returns an accessor. Anything that should update over time belongs in a *hole* (an accessor, a zero-argument callable, or a t-string placed in the tree), a memo, or an effect. See [Primitives, Reactive holes](../concepts/primitives.md#reactive-holes).

## Run-once bodies

The body of a `@component` function executes exactly once per mount. Its return value is mounted, and from then on updates flow through the reactive graph, never by calling the body again.

```python
from wybthon import Prop, Props, button, component, create_signal, div, p, prop


class CounterProps(Props):
    step: Prop[int] = prop(default=1)


@component
def Counter(props: CounterProps):
    print("body runs once")
    count, set_count = create_signal(0)
    return div(
        p(t"Count: {count}"),
        button("+", on_click=lambda: set_count(lambda n: n + props.step.peek())),
    )
```

Consequences:

- Local variables are stable. There's no need to memoize callbacks or worry about stale closures.
- `if` statements in the body run once. Use [`Show`][wybthon.Show] or [`Switch`][wybthon.Switch] for conditions that should track a signal.
- Reading a signal or prop at the top level of the body isn't tracked, and dev mode warns about it. When a one-time read is what you want, say so with `.peek()` or [`untrack`][wybthon.untrack].

## Declaring props

A component takes no parameters, or one parameter annotated with a subclass of [`Props`][wybthon.Props]. Each annotated field is an input:

```python
from collections.abc import Callable

from wybthon import Prop, Props, button, component, div, p, prop


class ToggleProps(Props):
    label: Prop[str]  # required, reactive
    initial: Prop[bool] = prop(default=False)  # optional, reactive
    tags: Prop[list[str]] = prop(default_factory=list)
    on_toggle: Callable[[bool], None] | None = None  # plain field: a callback


@component
def Toggle(props: ToggleProps):
    on = props.initial.peek()

    def flip():
        if props.on_toggle is not None:
            props.on_toggle(not on)

    return div(p(props.label), button("Toggle", on_click=flip))


@component
def App():
    return Toggle(label="Dark mode", on_toggle=lambda value: print("now", value))
```

- A **`Prop[T]` field** is reactive. The parent may pass a `T`, an accessor of `T`, or a zero-argument function returning `T`. Reading `props.label` returns an [`Accessor[T]`][wybthon.Accessor] that unwraps whichever it was.
- Defaults use **`prop(default=...)`**, or `prop(default_factory=...)` for mutable values. The keyword is required: type checkers only recognize a field default passed by keyword.
- **Any other annotation is a plain field.** `props.on_toggle` returns exactly what the parent passed, untracked, and the read never calls it. Declare callbacks, refs, and other values you hand on rather than display this way. Plain fields use ordinary defaults (`= None`).
- Every component also accepts **`key=`**, declared on the `Props` base.
- A component with **no inputs** takes no parameters: `def App():`.

In dev mode, calling a component with an unknown prop or without a required one raises `TypeError` at the call site. Pyright and mypy report the same mistakes statically; see the [Typing guide](typing.md).

## Holes

A hole is an accessor, a zero-argument callable, or a t-string placed in a child position. The reconciler runs it inside its own render effect and re-renders only its subtree when a dependency changes. A hole may return a VNode, a string, a list, `None`, or another accessor. `None`, `True`, and `False` render nothing, in child positions and as hole results alike, so `lambda: ready() and Panel()` works the way `{ready() && <Panel />}` does in JSX.

```python
from wybthon import component, create_memo, create_signal, div, p, span


@component
def Greeting():
    name, set_name = create_signal("Ada")
    letters = create_memo(lambda: len(name()))
    return div(
        p("Hello, ", name),  # accessor as a hole
        p(t"{name} has {letters} letters"),  # t-string: one binding
        span(lambda: p("long name") if len(name()) > 5 else None),  # conditional subtree
    )
```

A [t-string](https://peps.python.org/pep-0750/) is the shortest way to write reactive text. Interpolations that are accessors or zero-argument functions are called inside one binding, so the whole string updates together; other interpolations are formatted once, and conversions and format specs apply (`t"{price:.2f}"`). A t-string with no reactive interpolations is static text. Reach for a `lambda:` when the hole computes something other than text.

Keep holes small. A hole that returns a large subtree re-diffs that subtree on every change; a hole around a single text node patches one node. Use [`hole`][wybthon.hole] when you need an explicit `key` for a hole inside a fragment.

Attributes take holes too. An accessor, a zero-argument callable, or a t-string as an attribute value creates a per-attribute binding:

```python
from wybthon import a, button, create_signal, div

selected, set_selected = create_signal(False)
saving, set_saving = create_signal(False)
user_id, set_user_id = create_signal(1)

div(class_=lambda: "active" if selected() else "", hidden=lambda: not selected())
button("Save", disabled=saving)  # accessor as an attribute
a("Profile", href=t"/users/{user_id}")  # t-string attribute
```

`class_` also accepts a list or a dict of `{name: bool | accessor}`, and `style` accepts a dict whose values may be accessors.

## Event handlers

Handlers are `on_*` keywords. A handler may take the [`DomEvent`][wybthon.DomEvent] or no arguments at all; Wybthon checks the arity once when it registers the handler:

```python
from wybthon import button, create_signal, input_

text, set_text = create_signal("")

button("Clear", on_click=lambda: set_text(""))
input_(value=text, on_input=lambda e: set_text(e.target.value))
```

Handlers and refs are never treated as reactive expressions, so a zero-argument handler is safe anywhere.

## Reading a `Prop`: peek versus call

There are three ways to use a `Prop[T]` field:

| You want | Write |
| --- | --- |
| The value to stay live in the DOM | Place it in the tree: `p(props.name)` or `p(t"Hi, {props.name}")` |
| To derive from it | Call it inside a memo, effect, or hole: `lambda: props.name().upper()` |
| A one-time read (a seed, a config flag) | `props.name.peek()` |

```python
from wybthon import Prop, Props, component, create_memo, create_signal, div, p, prop


class ProfileProps(Props):
    name: Prop[str]
    initial_tab: Prop[str] = prop(default="info")


@component
def Profile(props: ProfileProps):
    tab, set_tab = create_signal(props.initial_tab.peek())  # seed: read once
    shout = create_memo(lambda: props.name().upper())  # derive: tracked read
    return div(p(props.name), p(shout), p(t"Tab: {tab}"))  # bind: place in tree
```

A parent may pass a plain value or an accessor; the child reads `props.name()` either way. Callbacks belong in plain fields, so there's no ambiguity between "a function to call" and "a reactive expression to read."

## Children

Declare children by subclassing [`ParentProps`][wybthon.ParentProps], which adds `children: Prop[Any]`. Place `props.children` in the tree to render it:

```python
from wybthon import ParentProps, Prop, component, h3, p, prop, section


class CardProps(ParentProps):
    title: Prop[str] = prop(default="")


@component
def Card(props: CardProps):
    return section(h3(props.title), props.children, class_="card")


Card(title="Composition")[p("Body text"), p("More text")]  # item syntax
Card(title="Composition", children=p("Body text"))  # keyword
```

Item syntax works on elements too: `div(class_="row")[span("a"), span("b")]`. Positional children (`Card(p("Body"), title="Composition")`) still work at run time, but type checkers don't validate them, so prefer the keyword or item syntax.

When a component needs to inspect or reorder its children, resolve them with the [`children`][wybthon.children] helper. It flattens nested lists, calls nested accessors and zero-argument functions, and drops `None` and booleans. Calling the result returns the single child or a list; `.to_array()` always returns a list:

```python
from wybthon import ParentProps, component, li, ul
from wybthon import children as resolve_children


@component
def Bullets(props: ParentProps):
    kids = resolve_children(props.children)
    return ul(lambda: [li(child) for child in kids.to_array()])
```

## Forwarding attributes with `merge` and `omit`

There's no `**rest`: a component reads only the props it declares. To forward attributes to an element, declare them and spread the remainder with [`omit`][wybthon.omit], which returns a reactive mapping without the named keys (or without the keys a predicate selects):

```python
from wybthon import ParentProps, Prop, component, omit, prop, section


class PanelProps(ParentProps):
    title: Prop[str] = prop(default="")
    id: Prop[str | None] = prop(default=None)
    hidden: Prop[bool] = prop(default=False)


@component
def Panel(props: PanelProps):
    return section(props.title, props.children, **omit(props, "title", "children"))
```

[`merge`][wybthon.merge] combines prop sources (props instances, dicts, or other views) into one reactive mapping; later sources win:

```python
from wybthon import Prop, Props, button, component, merge, omit, prop


class ButtonProps(Props):
    label: Prop[str]
    variant: Prop[str] = prop(default="solid")
    disabled: Prop[bool] = prop(default=False)


@component
def Button(props: ButtonProps):
    attrs = merge({"type": "button"}, omit(props, "label", "variant"))
    return button(props.label, class_=t"btn btn-{props.variant}", **attrs)
```

!!! warning "Pass handlers explicitly"
    Spread `merge` and `omit` views for attributes, not for event handlers. Every entry in the view is an accessor, so forward a callback by name instead: `button(..., on_click=props.on_click)`.

## Keyed remounts

A component stays mounted as long as its hole keeps returning a VNode with the same tag and key. To force a fresh mount when an identity changes (a different user, a different document), give the VNode a `key`:

```python
from wybthon import Prop, Props, component, create_signal, div, p


class DocumentViewProps(Props):
    doc_id: Prop[str]


@component
def DocumentView(props: DocumentViewProps):
    return p(t"Editing {props.doc_id}")


@component
def Editor():
    doc_id, set_doc_id = create_signal("a")
    return div(lambda: DocumentView(doc_id=doc_id(), key=doc_id()))
```

Without the key, `DocumentView` receives the new `doc_id` through its live prop and keeps its local state. With it, the old instance is disposed (cleanups run) and a new one mounts.

The same idea applies to `Show(when, children, keyed=True)` and `Match(when, children, keyed=True)`, which re-create the branch on every value change and hand the callback the raw value instead of an accessor.

## `dynamic`

[`dynamic`][wybthon.dynamic] turns an accessor for a component (or a tag name) into a component you call like any other. Each instance re-mounts when the resolved component changes; props and children are forwarded.

```python
from wybthon import component, create_signal, div, dynamic, h1, h3, li, ul


@component
def ListView():
    return ul(li("one"), li("two"))


@component
def GridView():
    return div("one", "two", class_="grid")


VIEWS = {"list": ListView, "grid": GridView}


@component
def Gallery():
    mode, set_mode = create_signal("list")
    View = dynamic(lambda: VIEWS[mode()])
    return div(View())


big, set_big = create_signal(True)
dynamic("h2")("Heading text")  # a tag name
dynamic(lambda: "h1" if big() else "h3")(children="Title")
```

## Refs

Pass a [`Ref`][wybthon.Ref] to an element's `ref=` prop. After mount, `ref.current` is an [`Element`][wybthon.Element] with `.element` for the raw node; it resets to `None` on unmount. Refs are assigned during mount, so read them in [`on_settled`][wybthon.on_settled] or an effect.

```python
from wybthon import Props, Ref, component, input_, on_settled


class AutoFocusInputProps(Props):
    ref: Ref | None = None  # plain field: handed on, never read reactively


@component
def AutoFocusInput(props: AutoFocusInputProps):
    local = Ref()
    on_settled(lambda: local.current.element.focus())
    # Forward the parent's ref (if any) alongside the local one.
    return input_(type="text", ref=[local, props.ref])
```

`ref=` also accepts a callback `ref(el)` and lists mixing refs and callbacks. There is no `forward_ref`; a ref is an ordinary plain field.

## Lifecycle

- [`on_settled`][wybthon.on_settled] runs once after the flush that mounted the component. The DOM is live and refs are assigned. Return a callable to register a cleanup.
- [`on_cleanup`][wybthon.on_cleanup] runs when the owning scope is disposed: on unmount for a component body, before each re-run inside an effect, and when a row leaves a `For`.
- [`create_effect`][wybthon.create_effect] runs after the DOM commit; its first run is deferred to the next flush. Prefer the split form `create_effect(compute, apply)` so incidental reads in the side effect don't over-subscribe.

```python
from wybthon import component, create_effect, create_signal, div, on_cleanup, on_settled


@component
def Ticker():
    seconds, set_seconds = create_signal(0)

    def start():
        from js import clearInterval, setInterval
        from pyodide.ffi import create_proxy

        proxy = create_proxy(lambda: set_seconds(lambda s: s + 1))
        handle = setInterval(proxy, 1000)
        return lambda: (clearInterval(handle), proxy.destroy())

    on_settled(start)
    create_effect(seconds, lambda value, prev: print("tick", prev, "->", value))
    on_cleanup(lambda: print("ticker unmounted"))
    return div(t"Seconds: {seconds}")
```

## Context

A [`Context`][wybthon.Context] is callable: `Theme(value, *children)` provides, [`use_context`][wybthon.use_context] reads. The value is handed to consumers exactly as provided, so pass an accessor when consumers should react to changes.

```python
from wybthon import button, component, create_context, create_signal, use_context

Theme = create_context("light")


@component
def ThemedButton():
    theme = use_context(Theme)
    return button("Hi", class_=t"btn-{theme}")


@component
def App():
    theme, set_theme = create_signal("dark")
    return Theme(theme, ThemedButton())
```

## Patterns checklist

- Declare inputs on a `Props` class: `Prop[T]` for values that can change, plain fields for callbacks and refs, `prop(default=...)` for defaults.
- Subclass `ParentProps` for components that render children; pass children with item syntax or the `children` keyword.
- Place accessors and t-strings in the tree; keep `lambda:` holes small.
- Seed local state with `props.x.peek()`; derive with `create_memo`.
- Forward attributes with `omit` and `merge`; pass handlers by name.
- Give VNodes a `key` when identity should force a remount.
- Use `For` for lists with a `keyed` strategy that matches your data; pass an accessor for `each`, never a plain list.
- Write signals from event handlers, actions, or the `apply` stage of a split effect, never inside a memo or hole.
- Use `on_settled` for DOM-dependent setup and return a cleanup from it.

## Next steps

- Read [Components](../concepts/components.md) and [Lifecycle and Ownership](../concepts/lifecycle.md).
- Browse the [Authoring patterns example](../examples/authoring-patterns.md) for a complete module.
- See the [`reactivity`][wybthon.reactivity] API for `merge`, `omit`, `children`, and friends.
