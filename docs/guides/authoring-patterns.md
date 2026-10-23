# Authoring patterns

This guide shows how to author components in Wybthon's run-once model, with recipes for the situations that come up in every app.

!!! tip "Mental model in one line"
    Components run **once**. Inputs are declared on a [`Props`][wybthon.Props] class with plain annotations, and reading `props.title` returns the value, tracked. Anything that should update over time is an expression in the markup, a memo, or an effect: the [compiler](../concepts/compiler.md) turns each dynamic expression in a template (`{count() * 2}`, `{props.title}`) into a getter, so only the text node or attribute that reads it updates.

The examples write markup with [`html`][wybthon.html] templates; see [Templates](../concepts/templates.md) for the syntax. Where markup is built by code, [`h(tag, props, *children)`][wybthon.h] is the programmatic layer, the counterpart of Solid's `h`.

## Run-once bodies

The body of a `@component` function executes exactly once per mount. Its return value is mounted, and from then on updates flow through the reactive graph, never by calling the body again.

```python
from wybthon import Props, component, create_signal, html


class CounterProps(Props):
    step: int = 1


@component
def Counter(props: CounterProps):
    print("body runs once")
    count, set_count = create_signal(0)

    def increment():
        set_count(lambda n: n + props.step)

    return html(t"""
      <div>
        <p>Count: {count()}</p>
        <button onclick={increment}>+</button>
      </div>
    """)
```

Consequences:

- Local variables are stable. There's no need to memoize callbacks or worry about stale closures.
- `if` statements in the body run once. Use [`Show`][wybthon.Show] or [`Switch`][wybthon.Switch] for conditions that should track a signal.
- Reading a signal or a reactive prop at the top level of the body isn't tracked, and dev mode warns about it. When a one-time read is what you want, say so with [`untrack`][wybthon.untrack] (`untrack(lambda: props.initial)`), or `.peek()` on a signal. Reading inside a handler, like `props.step` in `increment`, is fine: handlers run untracked.

## Declaring props

A component takes no parameters, or one parameter annotated with a subclass of [`Props`][wybthon.Props]. Each annotated field is an input:

```python
from collections.abc import Callable

from wybthon import Props, component, html, prop, untrack


class ToggleProps(Props):
    label: str  # required
    initial: bool = False  # optional
    tags: list[str] = prop(default_factory=list)
    on_toggle: Callable[[bool], None] | None = None  # a callback


@component
def Toggle(props: ToggleProps):
    on = untrack(lambda: props.initial)

    def flip():
        if props.on_toggle is not None:
            props.on_toggle(not on)

    return html(t"""
      <div>
        <p>{props.label}</p>
        <button onclick={flip}>Toggle</button>
      </div>
    """)


def report(value: bool) -> None:
    print("now", value)


@component
def App():
    return Toggle(label="Dark mode", on_toggle=report)
```

- **Fields are plain annotations.** Reading `props.label` returns the parent's current value and tracks it, as reading a property of Solid's props object does. In a template, `{props.label}` is dynamic, so the compiler makes it a getter and the text follows the parent.
- The parent may pass a value, an accessor, or (in a compiled template) a getter: `<{Toggle} label={user().name}>`. Getters and accessors are unwrapped on read, so the child sees a `str` either way.
- **Callable annotations are returned as passed.** A field annotated `Callable[...]` (or `Accessor[...]`, alone or in a union with `None`) returns exactly what the parent passed, and the read never calls it. Declare callbacks this way.
- Defaults are ordinary (`= False`, `= None`). Use **`prop(default_factory=...)`** for mutable values; the factory runs once per instance. Pass the keyword: type checkers only recognize a field specifier's default by keyword.
- Every component also accepts **`key=`**, declared on the `Props` base.
- A component with **no inputs** takes no parameters: `def App():`.

In dev mode, calling a component with an unknown prop or without a required one raises `TypeError` at the call site. Pyright and mypy report the same mistakes statically for calls like `Toggle(label=...)`, including calls inside a template's interpolations; see the [Typing guide](typing.md).

A prop that the parent passes as a constant costs nothing to read: a binding that reads nothing reactive allocates no computation. [`is_static(props, "label")`][wybthon.is_static] tells a component whether the parent passed a plain value, when a cheaper path is worth taking.

## Reactive expressions

Any interpolation in a template whose expression contains a call, an attribute access, or a subscript is **dynamic**: the compiler turns it into a getter. In a child position the getter becomes a *hole* that runs inside its own render effect and re-renders only its subtree when a dependency changes. A hole may produce a node, a string, a list, `None`, or an accessor. `None`, `True`, and `False` render nothing, so `{ready() and Panel()}` works the way `{ready() && <Panel />}` does in JSX.

```python
from wybthon import component, create_memo, create_signal, html


@component
def Greeting():
    name, set_name = create_signal("Ada")
    letters = create_memo(lambda: len(name()))

    return html(t"""
      <div>
        <p>Hello, {name()}</p>
        <p>{name()} has {letters()} letters</p>
        {html(t"<p>That's a long name.</p>") if letters() > 5 else None}
      </div>
    """)
```

`{name()}` and `{letters()}` each update one text node; the text around them is static markup. The conditional mounts or removes a subtree. Names, constants, and lambdas aren't wrapped: an accessor placed directly (`{name}`) still binds reactively, and anything else that isn't callable is applied once. Conversions and format specs fold into the getter (`{price():.2f}`).

A function call in a child position is dispatched when the template is created: a component or built-in (`{Card(title=user().name)}`, `{Show(...)}`, `{For(...)}`) is built with a getter for each dynamic argument, and any other call (`{badge(user())}`, `{str(n())}`) becomes one reactive hole. See [The compiler](../concepts/compiler.md) for the full rule.

Keep holes small. A hole that produces a subtree runs again on every change: if it returns a template from the same literal, Wybthon patches the mounted instance slot by slot, but anything else is rebuilt. A hole around a single text node patches one node. Use [`hole`][wybthon.hole] when you need an explicit `key` for a hole inside a fragment.

Attributes work the same way. A dynamic expression as an attribute value creates a per-attribute binding, and an attribute that mixes text with interpolations becomes one binding:

```python
from wybthon import create_signal, html

selected, set_selected = create_signal(False)
saving, set_saving = create_signal(False)
user_id, set_user_id = create_signal(1)

html(t"""
  <div class={"active" if selected() else ""} hidden={not selected()}>
    <button disabled={saving()}>Save</button>
    <a href="/users/{user_id()}">Profile</a>
  </div>
""")
```

`class` also accepts a list or a dict of `{name: bool}`, and `style` accepts a dict. Write a literal dict with spaces inside the braces (`class={ {"card": True, "active": active()} }`), because `{{` in a t-string is an escaped brace, or give it a name.

## Event handlers

In a template, a handler is an `on` attribute: `onclick`, `onClick`, and `on:click` all bind a delegated `click` handler. With `h()`, use `on_*` keys (`{"on_click": save}`). A handler may take the [`DomEvent`][wybthon.DomEvent] or no arguments at all; Wybthon checks the arity once when it registers the handler:

```python
from wybthon import create_signal, html

text, set_text = create_signal("")


def clear():
    set_text("")


def update(e):
    set_text(e.target.value)


html(t"""
  <input value={text()} oninput={update}>
  <button onclick={clear}>Clear</button>
""")
```

The compiler never wraps handlers or refs, so `onclick={props.on_close}` passes the callback itself. A named handler reads better than an inline one; when you do write a lambda inline, Python requires parentheses: `onclick={(lambda: set_open(False))}`.

## Reading props

| You want | Write |
| --- | --- |
| The value to stay live in the DOM | Place it in the markup: `<p>{props.name}</p>` or `<p>Hi, {props.name}</p>` |
| To derive from it | Read it inside a memo or effect: `create_memo(lambda: props.name.upper())` |
| A one-time read (a seed, a config flag) | `untrack(lambda: props.name)` |

```python
from wybthon import Props, component, create_memo, create_signal, html, untrack


class ProfileProps(Props):
    name: str
    initial_tab: str = "info"


@component
def Profile(props: ProfileProps):
    tab, set_tab = create_signal(untrack(lambda: props.initial_tab))  # seed: read once
    shout = create_memo(lambda: props.name.upper())  # derive: tracked read
    return html(t"""
      <div>
        <p>{props.name}</p>
        <p>{shout()}</p>
        <p>Tab: {tab()}</p>
      </div>
    """)  # bind: place in the markup
```

Passing a prop through to a child stays reactive without any care on your part: `<{Avatar} name={props.name}>` hands the child a getter, so the child reads the parent's current value.

## Children

Declare children by subclassing [`ParentProps`][wybthon.ParentProps], which adds `children: Any = None`. Place `props.children` in the markup to render it:

```python
from wybthon import ParentProps, component, html


class CardProps(ParentProps):
    title: str = ""


@component
def Card(props: CardProps):
    return html(t'<section class="card"><h3>{props.title}</h3>{props.children}</section>')


html(t"""
  <{Card} title="Composition">
    <p>Body text</p>
    <p>More text</p>
  </{Card}>
""")  # tag form: nested markup is the children
Card(title="Composition")[html(t"<p>Body text</p><p>More text</p>")]  # item syntax
Card(title="Composition", children=html(t"<p>Body text</p>"))  # keyword
```

The tag form reads like the rest of the markup, but type checkers can't see its props; dev mode checks them at run time. The call forms are fully type-checked, and the keyword form works inside a template too: `{Card(title=user().name, children=html(t"<p>Body</p>"))}`. Positional children (`Card(html(t"<p>Body</p>"), title="Composition")`) still work at run time, but type checkers don't validate them, so prefer the keyword or item syntax.

When a component needs to inspect or reorder its children, resolve them with the [`children`][wybthon.children] helper. It takes a getter, flattens nested lists, calls nested accessors, and drops `None` and booleans. Calling the result returns the single child or a list; `.to_array()` always returns a list:

```python
from wybthon import ParentProps, component, html
from wybthon import children as resolve_children


@component
def Bullets(props: ParentProps):
    kids = resolve_children(lambda: props.children)
    return html(t"<ul>{[html(t'<li>{child}</li>') for child in kids.to_array()]}</ul>")
```

## Forwarding attributes with `merge` and `omit`

There's no `**rest`: a component reads only the props it declares. To forward attributes to an element, declare them and spread the remainder with [`omit`][wybthon.omit], which returns a reactive view without the named keys (or without the keys a predicate selects). In a template, a bare `{attrs}` inside a tag spreads a mapping, binding each key reactively:

```python
from wybthon import ParentProps, component, html, omit


class PanelProps(ParentProps):
    title: str = ""
    id: str | None = None
    hidden: bool = False


@component
def Panel(props: PanelProps):
    attrs = omit(props, "title", "children")
    return html(t"<section {attrs}><h3>{props.title}</h3>{props.children}</section>")
```

[`merge`][wybthon.merge] combines prop sources (props instances, dicts, or other views) into one reactive view; later sources win:

```python
from collections.abc import Callable

from wybthon import Props, component, html, merge, omit


class ButtonProps(Props):
    label: str
    variant: str = "solid"
    disabled: bool = False
    on_click: Callable[[], None] | None = None


@component
def Button(props: ButtonProps):
    attrs = merge({"type": "button"}, omit(props, "label", "variant"))
    return html(t'<button class="btn btn-{props.variant}" {attrs}>{props.label}</button>')
```

A view reads like props: `attrs.disabled` is the tracked value. Spreading binds attributes reactively and passes event handlers and refs through as the callables themselves, so `on_click` above reaches the button as a click handler. With `h()`, pass the view as the props: `h("section", omit(props, "title", "children"), ...)`.

## Keyed remounts

A component stays mounted as long as its hole keeps returning a node with the same tag and key. To force a fresh mount when an identity changes (a different user, a different document), give the node a `key`:

```python
from wybthon import Props, component, create_signal, html


class DocumentViewProps(Props):
    doc_id: str


@component
def DocumentView(props: DocumentViewProps):
    return html(t"<p>Editing {props.doc_id}</p>")


@component
def Editor():
    doc_id, set_doc_id = create_signal("a")

    def view():
        return DocumentView(doc_id=doc_id(), key=doc_id())

    return html(t"<div>{view()}</div>")
```

`{view()}` is a call without arguments, so it's one reactive hole. When `doc_id` changes, the hole returns a node with a new key: the old instance is disposed (cleanups run) and a new one mounts. Without the key, the hole would patch the mounted `DocumentView` with the new `doc_id`, and it would keep its local state. Writing `{DocumentView(doc_id=doc_id())}` directly in the markup needs no hole at all: the component is built once and reads `doc_id` through a getter.

The same idea applies to `Show(when, children, keyed=True)` and `Match(when, children, keyed=True)`, which re-create the branch on every value change and hand the callback the raw value instead of an accessor.

## `dynamic`

[`dynamic`][wybthon.dynamic] turns an accessor for a component (or a tag name) into a component you call like any other. Each instance re-mounts when the resolved component changes; props and children are forwarded.

```python
from wybthon import component, create_signal, dynamic, html


@component
def ListView():
    return html(t"<ul><li>one</li><li>two</li></ul>")


@component
def GridView():
    return html(t'<div class="grid">one two</div>')


VIEWS = {"list": ListView, "grid": GridView}


@component
def Gallery():
    mode, set_mode = create_signal("list")
    View = dynamic(lambda: VIEWS[mode()])
    return html(t"<div>{View()}</div>")


big, set_big = create_signal(True)
dynamic("h2")("Heading text")  # a tag name
dynamic(lambda: "h1" if big() else "h3")(children="Title")
```

## Refs

Pass a [`Ref`][wybthon.Ref] to an element's `ref` attribute. After mount, `ref.current` is an [`Element`][wybthon.Element] with `.element` for the raw node; it resets to `None` on unmount. Refs are assigned during mount, so read them in [`on_settled`][wybthon.on_settled] or an effect.

```python
from wybthon import Props, Ref, component, html, on_settled


class AutoFocusInputProps(Props):
    ref: Ref | None = None


@component
def AutoFocusInput(props: AutoFocusInputProps):
    local = Ref()
    on_settled(lambda: local.current.element.focus())
    # Forward the parent's ref (if any) alongside the local one.
    return html(t'<input type="text" ref={[local, props.ref]}>')
```

`ref` also accepts a callback that receives the `Element` (`ref={remember}`), and lists mixing refs and callbacks. There's no `forward_ref`; a ref is an ordinary field.

## Lifecycle

- [`on_settled`][wybthon.on_settled] runs once after the flush that mounted the component. The DOM is live and refs are assigned. Return a callable to register a cleanup.
- [`on_cleanup`][wybthon.on_cleanup] runs when the owning scope is disposed: on unmount for a component body, before each re-run inside an effect, and when a row leaves a `For`.
- [`create_effect`][wybthon.create_effect] runs after the DOM commit; its first run is deferred to the next flush. Prefer the split form `create_effect(compute, apply)` so incidental reads in the side effect don't over-subscribe.

```python
from wybthon import component, create_effect, create_signal, html, on_cleanup, on_settled


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
    return html(t"<div>Seconds: {seconds()}</div>")
```

## Context

A [`Context`][wybthon.Context] is callable: `Theme(value, *children)` provides, [`use_context`][wybthon.use_context] reads. The value is handed to consumers exactly as provided, so pass an accessor when consumers should react to changes.

```python
from wybthon import component, create_context, create_signal, html, use_context

Theme = create_context("light")


@component
def ThemedButton():
    theme = use_context(Theme)
    return html(t'<button class="btn-{theme()}">Hi</button>')


@component
def App():
    theme, set_theme = create_signal("dark")
    return Theme(theme, ThemedButton())
```

## Patterns checklist

- Declare inputs on a `Props` class with plain annotations; annotate callbacks `Callable[...]`; use `prop(default_factory=...)` for mutable defaults.
- Subclass `ParentProps` for components that render children; pass children with the `<{Card}>` tag form, item syntax, or the `children` keyword.
- Write expressions directly in the markup (`{count() * 2}`, `{props.title}`); the compiler keeps them reactive.
- Seed local state with `untrack(lambda: props.x)`; derive with `create_memo`.
- Forward attributes with `omit` and `merge`.
- Give nodes a `key` when identity should force a remount.
- Use `For` for lists with a `keyed` strategy that matches your data: `{For(todos(), todo_row)}` in a template, or `For(todos, todo_row)` in Python code (pass the accessor, not a plain list).
- Write signals from event handlers, actions, or the `apply` stage of a split effect, never inside a memo or hole.
- Use `on_settled` for DOM-dependent setup and return a cleanup from it.

## Next steps

- Read [Templates](../concepts/templates.md), [The compiler](../concepts/compiler.md), [Components](../concepts/components.md), and [Lifecycle and Ownership](../concepts/lifecycle.md).
- Browse the [Authoring patterns example](../examples/authoring-patterns.md) for a complete module.
- See the [`reactivity`][wybthon.reactivity] API for `merge`, `omit`, `children`, and friends.
