# Authoring patterns

This guide shows how to author components in Wybthon's run-once model, with recipes for the situations that come up in every app.

!!! tip "Mental model in one line"
    Components run **once**. Every parameter is a [`Prop[T]`][wybthon.Prop] accessor. Anything that should update over time belongs in a *hole* (a zero-argument callable or accessor placed in the tree), a memo, or an effect. See [Primitives, Reactive holes](../concepts/primitives.md#reactive-holes).

## Run-once bodies

The body of a `@component` function executes exactly once per mount. Its return value is mounted, and from then on updates flow through the reactive graph, never by calling the body again.

```python
from wybthon import Prop, button, component, create_signal, div, p, prop


@component
def Counter(step: Prop[int] = prop(1)):
    print("body runs once")
    count, set_count = create_signal(0)
    return div(
        p("Count: ", count),
        button("+", on_click=lambda e: set_count(lambda n: n + step())),
    )
```

Consequences:

- Local variables are stable. There's no need to memoize callbacks or worry about stale closures.
- `if` statements in the body run once. Use [`Show`][wybthon.Show] or [`Switch`][wybthon.Switch] for conditions that should track a signal.
- Reading a signal or prop at the top level of the body isn't tracked, and dev mode warns about it. When a one-time read is what you want, say so with `.peek()` or [`untrack`][wybthon.untrack].

## Holes

A hole is a zero-argument callable or an accessor placed in a child position. The reconciler runs it inside its own render effect and re-renders only its subtree when a dependency changes. A hole may return a VNode, a string, a list, `None`, or another accessor. `None`, `True`, and `False` render nothing, in child positions and as hole results alike, so `lambda: ready() and Panel()` works the way `{ready() && <Panel />}` does in JSX.

```python
from wybthon import component, create_signal, div, p, span


@component
def Greeting():
    name, set_name = create_signal("Ada")
    return div(
        p("Hello, ", name),                               # accessor as a hole
        p(lambda: f"{len(name())} letters"),              # expression as a hole
        span(lambda: p("long name") if len(name()) > 5 else None),  # conditional subtree
    )
```

Keep holes small. A hole that returns a large subtree re-diffs that subtree on every change; a hole around a single text node patches one node. Use [`hole`][wybthon.hole] when you need an explicit `key` for a hole inside a fragment.

Props take holes too. An accessor or zero-argument callable as a prop value creates a per-prop binding:

```python
from wybthon import button, div

div(class_=lambda: "active" if selected() else "", hidden=lambda: not visible())
button("Save", disabled=saving)  # accessor as a prop
```

`class_` also accepts a list or a dict of `{name: bool | accessor}`, and `style` accepts a dict whose values may be accessors.

## `Prop`: peek versus call

Every parameter is a `Prop`. There are three ways to use one:

| You want | Write |
| --- | --- |
| The value to stay live in the DOM | Place the prop in the tree: `p(name)` |
| To derive from it | Call it inside a memo, effect, or hole: `lambda: name().upper()` |
| A one-time read (a seed, a config flag) | `name.peek()` |

```python
from wybthon import Prop, component, create_memo, create_signal, div, p, prop


@component
def Profile(name: Prop[str], initial_tab: Prop[str] = prop("info")):
    tab, set_tab = create_signal(initial_tab.peek())    # seed: read once
    shout = create_memo(lambda: name().upper())          # derive: tracked read
    return div(p(name), p(shout), p("Tab: ", tab))       # bind: place in tree
```

A parent may pass a plain value or an accessor; the child reads `name()` either way. Callbacks that take arguments (`on_select=handler`) aren't treated as reactive expressions and arrive unchanged when you call the prop: `on_select()(item)`.

!!! note "Callbacks with no arguments"
    Only zero-argument callables count as reactive expressions. If you need to pass a zero-argument callback as a prop, read it with `props.raw("name")` in a `props`-style component, or wrap it so the prop yields the function: `on_done=lambda: done` and `on_done()()`.

## `**rest` pass-through

Declare the props you handle and forward the rest. Undeclared props arrive in `**rest` as `Prop` accessors, which spread straight onto an element:

```python
from wybthon import Prop, button, component, prop


@component
def IconButton(icon: Prop[str], label: Prop[str] = prop(""), **rest):
    return button(icon, " ", label, type="button", **rest)


IconButton(icon="*", label="Star", class_="primary", on_click=lambda e: print("clicked"))
```

## `merge` and `omit`

[`merge`][wybthon.merge] combines prop sources into one reactive mapping (later sources win); [`omit`][wybthon.omit] returns a view without certain keys. Both replace the old `merge_props` and `split_props` helpers.

```python
from wybthon import Prop, Props, button, component, div, merge, omit, prop


@component
def Button(variant: Prop[str] = prop("solid"), **rest):
    attrs = merge({"type": "button"}, rest)
    return button(**attrs, class_=lambda: f"btn btn-{variant()}")


@component
def Panel(props: Props):
    return div(props.children, **omit(props, "children", "title"))
```

A component whose only parameter is named `props` (or annotated `Props`) receives the whole [`Props`][wybthon.Props] mapping. `props.title` and `props["title"]` return the accessor; `props.raw("title")` returns the value exactly as the parent passed it.

## `children()`

The `children` prop holds whatever the parent passed positionally. For layouts that render it once, place the prop in the tree. To resolve nested lists and drop `None` entries in a memoized way, use the [`children`][wybthon.children] helper (import it under another name to avoid shadowing the parameter):

```python
from wybthon import Prop, component, h3, prop, section
from wybthon import children as resolve_children


@component
def Card(title: Prop[str] = prop(""), children: Prop = prop(None)):
    kids = resolve_children(children)
    return section(h3(title), kids, class_="card")


Card("Body text", title="Composition")
```

## Keyed remounts

A component stays mounted as long as its hole keeps returning a VNode with the same tag and key. To force a fresh mount when an identity changes (a different user, a different document), give the VNode a `key`:

```python
from wybthon import component, create_signal, div


@component
def Editor():
    doc_id, set_doc_id = create_signal("a")
    return div(lambda: DocumentView(doc_id=doc_id(), key=doc_id()))
```

Without the key, `DocumentView` receives the new `doc_id` through its live `Prop` and keeps its local state. With it, the old instance is disposed (cleanups run) and a new one mounts.

The same idea applies to `Show(when, children, keyed=True)` and `Match(when, children, keyed=True)`, which re-create the branch on every value change and hand the callback the raw value instead of an accessor.

## `Dynamic`

[`Dynamic`][wybthon.Dynamic] renders a component or tag chosen at runtime. The subtree re-mounts when the resolved component changes; other props are forwarded.

```python
from wybthon import Dynamic, component, create_signal, div

VIEWS = {"list": ListView, "grid": GridView}


@component
def Gallery():
    mode, set_mode = create_signal("list")
    return div(Dynamic(lambda: VIEWS[mode()], items=items))


Dynamic("h2", "Heading text")            # a tag name
Dynamic(lambda: "h1" if big() else "h3", children="Title")
```

## Refs

Pass a [`Ref`][wybthon.Ref] to an element's `ref=` prop. After mount, `ref.current` is an [`Element`][wybthon.Element] with `.element` for the raw node; it resets to `None` on unmount. Refs are assigned during mount, so read them in [`on_settled`][wybthon.on_settled] or an effect.

```python
from wybthon import Prop, Ref, component, input_, on_settled, prop


@component
def AutoFocusInput(ref: Prop[Ref | None] = prop(None)):
    local = Ref()
    on_settled(lambda: local.current.element.focus())
    # Forward the parent's ref (if any) alongside the local one.
    return input_(type="text", ref=[local, ref.peek()])
```

`ref=` also accepts a callback `ref(el)` and lists mixing refs and callbacks. There is no `forward_ref`; a `ref` prop is an ordinary prop.

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
    return div(lambda: f"Seconds: {seconds()}")
```

## Context

A [`Context`][wybthon.Context] is callable: `Theme(value, *children)` provides, [`use_context`][wybthon.use_context] reads. The value is handed to consumers exactly as provided, so pass an accessor when consumers should react to changes.

```python
from wybthon import Context, button, component, create_context, create_signal, use_context

Theme = create_context("light")


@component
def ThemedButton():
    theme = use_context(Theme)
    return button("Hi", class_=lambda: f"btn-{theme()}")


@component
def App():
    theme, set_theme = create_signal("dark")
    return Theme(theme, ThemedButton())
```

## Patterns checklist

- Use `@component` for every function component; declare defaults with `prop()`.
- Place accessors and small lambdas in the tree; keep holes small.
- Seed local state with `prop.peek()`; derive with `create_memo`.
- Forward unknown props with `**rest`; shape them with `merge` and `omit`.
- Give VNodes a `key` when identity should force a remount.
- Use `For` for lists with a `keyed` strategy that matches your data; pass an accessor for `each`, never a plain list.
- Write signals from event handlers, actions, or the `apply` stage of a split effect, never inside a memo or hole.
- Use `on_settled` for DOM-dependent setup and return a cleanup from it.

## Next steps

- Read [Components](../concepts/components.md) and [Lifecycle and Ownership](../concepts/lifecycle.md).
- Browse the [Authoring patterns example](../examples/authoring-patterns.md) for a complete module.
- See the [`reactivity`][wybthon.reactivity] API for `merge`, `omit`, `children`, and friends.
