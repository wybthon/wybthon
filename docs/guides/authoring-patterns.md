# Authoring patterns

This guide shows how to author components in Wybthon's run-once model, with recipes for the situations that come up in every app.

!!! tip "Mental model in one line"
    Components run **once**. Inputs are ordinary function parameters, and reading one, `title`, returns the parent's current value, tracked. Anything that should update over time is an expression in the markup, a memo, or an effect: the [compiler](../concepts/compiler.md) turns each dynamic expression in a template (`{count() * 2}`, `{title}`) into a getter, so only the text node or attribute that reads it updates.

The examples write markup with [`html`][wybthon.html] templates; see [Templates](../concepts/templates.md) for the syntax. Where markup is built by code, [`h(tag, props, *children)`][wybthon.vnode.h] is the programmatic layer, the counterpart of Solid's `h`.

## Run-once bodies

The body of a `@component` function executes exactly once per mount. Its return value is mounted, and from then on updates flow through the reactive graph, never by calling the body again.

```python
from wybthon import component, create_signal, html


@component
def Counter(step: int = 1):
    print("body runs once")
    count, set_count = create_signal(0)

    def increment():
        set_count(lambda n: n + step)

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
- Reading a signal or a reactive parameter at the top level of the body isn't tracked, and dev mode warns about it. When a one-time read is what you want, say so with [`untrack`][wybthon.untrack] (`untrack(lambda: initial)`), or `.peek()` on a signal. Reading inside a handler, like `step` in `increment`, is fine: handlers run untracked and read the latest value when they run.

## Declaring props

A component's parameters are its props. Declare each input as an ordinary parameter with an annotation and, when it's optional, a default:

```python
from collections.abc import Callable

from wybthon import component, html, prop, untrack


@component
def Toggle(
    label: str,
    initial: bool = False,
    tags: list[str] = prop(default_factory=list),
    on_toggle: Callable[[bool], None] | None = None,
):
    on = untrack(lambda: initial)

    def flip():
        if on_toggle is not None:
            on_toggle(not on)

    return html(t"""
      <div>
        <p>{label}</p>
        <button onclick={flip}>Toggle</button>
      </div>
    """)


def report(value: bool) -> None:
    print("now", value)


@component
def App():
    return Toggle(label="Dark mode", on_toggle=report)
```

- **Parameters are props.** The compiler rewrites every read of a parameter in the body, so reading `label` returns the parent's current value and tracks it, as reading a property of Solid's props object does. In a template, `{label}` is dynamic (unlike other bare names), so the compiler makes it a getter and the text follows the parent.
- The parent may pass a value, an accessor, or (in a compiled template) a getter: `<{Toggle} label={user().name}>`. Getters and accessors are unwrapped on read, so the child sees a `str` either way.
- **Callable annotations are returned as passed.** A parameter annotated `Callable[...]` (or `Accessor[...]`, alone or in a union with `None`) reads as exactly what the parent passed, and the read never calls it. Declare callbacks this way.
- **Defaults are ordinary** (`= False`, `= None`). Use [`prop(default_factory=...)`][wybthon.prop] for mutable values; the factory runs once per instance.
- **Parameters are read-only.** Assigning to one, `del`, or declaring one `nonlocal` is a `SyntaxError` when the module is compiled; give the value a new name instead.
- **Arguments bind as in a Python call.** `Toggle("Dark mode")` is `Toggle(label="Dark mode")`. Positional arguments are never children; see [Children](#children).
- A component with **no inputs** takes no parameters: `def App():`.

In dev mode, calling a component with an unknown prop or without a required one raises `TypeError` at the call site. Pyright, Pylance, and mypy report the same mistakes statically, because a type checker sees an `@component` as the function itself: a call like `Toggle(label=...)` is checked against `Toggle`'s own signature, including calls inside a template's interpolations. See the [Typing guide](typing.md).

The compiler gives parameters their meaning, so a component's module must be compiled, as a module with templates must be. The import hook that `import wybthon` installs compiles every module imported after it, and `wyb build`, `wyb dev`, `wyb run`, and Wybthon's pytest plugin compile the modules they load. In dev mode, calling an uncompiled component that has parameters raises `TypeError`.

A prop that the parent passes as a constant costs nothing to read: a binding that reads nothing reactive allocates no computation. [`is_static(label)`][wybthon.is_static] tells a component whether the parent passed a plain value, when a cheaper path is worth taking; pass the parameter itself, and the compiler turns the call into a question about the prop.

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

`{name()}` and `{letters()}` each update one text node; the text around them is static markup. The conditional mounts or removes a subtree. Names, constants, and lambdas aren't wrapped: an accessor placed directly (`{name}`) still binds reactively, and anything else that isn't callable is applied once. A component's own parameters are the exception: a bare parameter is a read of a prop, so it's dynamic. Conversions and format specs fold into the getter (`{price():.2f}`).

A function call in a child position is dispatched when the template is created: a component or built-in (`{Card(title=user().name)}`, `{Show(...)}`, `{For(...)}`) is built with a getter for each dynamic argument, and any other call (`{badge(user())}`, `{str(n())}`) becomes one reactive hole. See [The compiler](../concepts/compiler.md) for the full rule.

The content and fallback of `Show`, `Match`, `Switch`, `Loading`, `Errored`, and `client_only` are lazy when they're written as markup or as a component call (a capitalized callee, such as `{Show(open(), Panel())}`): the compiler makes each a zero-argument function, so a branch's markup and components are built only when it shows, as JSX children are in Solid. Names, lambdas, and lowercase calls are passed as written.

Keep holes small. A hole that produces a subtree runs again on every change: if it returns a template from the same literal, Wybthon patches the mounted instance slot by slot, but anything else is rebuilt. A hole around a single text node patches one node. Use [`hole`][wybthon.vnode.hole] when you need an explicit `key` for a hole inside a fragment.

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

The compiler never wraps handlers or refs, so `onclick={on_close}` passes the parent's callback itself. A named handler reads better than an inline one; when you do write a lambda inline, Python requires parentheses: `onclick={(lambda: set_open(False))}`.

## Reading props

| You want | Write |
| --- | --- |
| The value to stay live in the DOM | Place it in the markup: `<p>{name}</p>` or `<p>Hi, {name}</p>` |
| To derive from it | Read it inside a memo or effect: `create_memo(lambda: name.upper())` |
| A one-time read (a seed, a config flag) | `untrack(lambda: name)` |

```python
from wybthon import component, create_memo, create_signal, html, untrack


@component
def Profile(name: str, initial_tab: str = "info"):
    tab, set_tab = create_signal(untrack(lambda: initial_tab))  # seed: read once
    shout = create_memo(lambda: name.upper())  # derive: tracked read
    return html(t"""
      <div>
        <p>{name}</p>
        <p>{shout()}</p>
        <p>Tab: {tab()}</p>
      </div>
    """)  # bind: place in the markup
```

Passing a parameter through to a child stays reactive without any care on your part: `<{Avatar} name={name}>` hands the child a getter, so the child reads the parent's current value. Reading a parameter at the top level of the body, as in `greeting = f"Hi, {name}"`, reads it once, as destructuring props does in Solid; dev mode warns when the value was reactive.

## Children

Declare a `children` parameter to accept children, annotated with [`Children`][wybthon.Children] (an alias of `Any`, for documentation): `children: Children = None`. Place `{children}` in the markup to render it:

```python
from wybthon import Children, component, html


@component
def Card(title: str = "", children: Children = None):
    return html(t'<section class="card"><h3>{title}</h3>{children}</section>')


html(t"""
  <{Card} title="Composition">
    <p>Body text</p>
    <p>More text</p>
  </{Card}>
""")  # tag form: nested markup is the children
Card(title="Composition")[html(t"<p>Body text</p><p>More text</p>")]  # item syntax
Card(title="Composition", children=html(t"<p>Body text</p>"))  # keyword
```

The tag form reads like the rest of the markup, but type checkers can't see its props on their own; `wyb check` checks them, and dev mode checks them at run time. The call forms are fully type-checked, and the keyword form works inside a template too: `{Card(title=user().name, children=html(t"<p>Body</p>"))}`. Positional arguments aren't children: they bind to parameters in order, so `Card("Composition")` passes the title. A component can't take `*args`.

When a component needs to inspect or reorder its children, resolve them with the [`resolve_children`][wybthon.resolve_children] helper. It takes a getter, flattens nested lists, calls nested accessors, and drops `None` and booleans. Calling the result returns the single child or a list; `.to_array()` always returns a list:

```python
from wybthon import Children, component, html, resolve_children


@component
def Bullets(children: Children = None):
    kids = resolve_children(lambda: children)
    return html(t"<ul>{[html(t'<li>{child}</li>') for child in kids.to_array()]}</ul>")
```

## Forwarding attributes with `**rest`, `merge`, and `omit`

A component accepts only the props it declares, unless it takes a `**rest` parameter. A `**rest` parameter (any name, such as `**attrs: Any`) collects the props the component doesn't declare as a reactive, read-only view. In a template, a bare `{attrs}` inside a tag spreads it, binding each key reactively:

```python
from typing import Any

from wybthon import Children, component, html


@component
def Panel(title: str = "", children: Children = None, **attrs: Any):
    return html(t"<section {attrs}><h3>{title}</h3>{children}</section>")


html(t'<{Panel} title="Details" id="details" hidden={collapsed()}><p>Body</p></{Panel}>')
```

`id` and `hidden` aren't parameters, so they land in `attrs` and on the `<section>`, and `hidden` follows `collapsed()`. A `None` value removes the attribute.

[`merge`][wybthon.merge] combines sources (dicts, `**rest` views, and other views) into one reactive view; later sources win. [`omit`][wybthon.omit] returns a view without the named keys (or without the keys a predicate selects):

```python
from typing import Any

from wybthon import component, html, merge, omit


@component
def Button(label: str, variant: str = "solid", **attrs: Any):
    forwarded = merge({"type": "button"}, omit(attrs, "title"))
    return html(t'<button class="btn btn-{variant}" {forwarded}>{label}</button>')
```

A view reads like props: `attrs.disabled` is the tracked value. Spreading binds attributes reactively and passes event handlers and refs through as the callables themselves, so `{Button(label="Save", on_click=save, disabled=saving())}` gives the button a click handler and a live `disabled` attribute. To ask whether the parent passed one of the forwarded props as a plain value, use `is_static(attrs, "disabled")`. With `h()`, pass the view as the props: `h("section", attrs, ...)`.

## Keyed remounts

A component stays mounted while the props it reads change: a parameter reads the parent's current value, and the component keeps its local state. To force a fresh mount when an identity changes (a different user, a different document), show the component through a keyed [`Show`][wybthon.Show], as in Solid:

```python
from wybthon import Show, component, create_signal, html


@component
def DocumentView(doc_id: str):
    draft, set_draft = create_signal("")  # fresh for each document
    return html(t"<p>Editing {doc_id}: {draft()}</p>")


@component
def Editor():
    doc_id, set_doc_id = create_signal("a")
    return html(t"<div>{Show(doc_id(), lambda current: DocumentView(doc_id=current), keyed=True)}</div>")
```

With `keyed=True`, `Show` re-creates its branch whenever the value changes and hands the callback the raw value instead of an accessor: the old instance is disposed (cleanups run) and a new one mounts. `Match(when, children, keyed=True)` does the same inside a `Switch`. Writing `{DocumentView(doc_id=doc_id())}` directly in the markup keeps one instance: it reads `doc_id` through a getter and keeps its draft.

Components don't take a `key`. For lists, use `For`, which keeps one instance per item. [`h(tag, {"key": ...})`][wybthon.vnode.h] still keys any node, as a low-level escape hatch.

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
from wybthon import Ref, component, html, on_settled


@component
def AutoFocusInput(ref: Ref | None = None):
    local = Ref()
    on_settled(lambda: local.current.element.focus())
    # Forward the parent's ref (if any) alongside the local one.
    return html(t'<input type="text" ref={[local, ref]}>')
```

`ref` also accepts a callback that receives the `Element` (`ref={remember}`), and lists mixing refs and callbacks. There's no `forward_ref`; a ref is an ordinary parameter.

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

- Declare inputs as annotated parameters; annotate callbacks `Callable[...]`; use `prop(default_factory=...)` for mutable defaults.
- Declare `children: Children = None` for components that render children; pass children with the `<{Card}>` tag form, item syntax, or the `children` keyword.
- Write expressions directly in the markup (`{count() * 2}`, `{title}`); the compiler keeps them reactive.
- Seed local state with `untrack(lambda: initial)`; derive with `create_memo`.
- Forward attributes with a `**rest` parameter, `merge`, and `omit`.
- Use a keyed `Show` when identity should force a remount.
- Use `For` for lists with a `keyed` strategy that matches your data: `{For(todos(), todo_row)}` in a template, or `For(todos, todo_row)` in Python code (pass the accessor, not a plain list).
- Write signals from event handlers, actions, or the `apply` stage of a split effect, never inside a memo or hole.
- Use `on_settled` for DOM-dependent setup and return a cleanup from it.

## Next steps

- Read [Templates](../concepts/templates.md), [The compiler](../concepts/compiler.md), [Components](../concepts/components.md), and [Lifecycle and Ownership](../concepts/lifecycle.md).
- Browse the [Authoring patterns example](../examples/authoring-patterns.md) for a complete module.
- See the [`reactivity`][wybthon.reactivity] API for `merge`, `omit`, `resolve_children`, and friends.
