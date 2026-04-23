### Authoring Patterns

This guide shows how to author components in Wybthon's
fully-reactive `@component` model.

> **Mental model in one line:** Components run **once**.  Every prop
> is a zero-arg accessor.  Reactivity happens through *reactive holes*
> — accessors (or `dynamic(...)` getters) embedded in the returned
> VNode tree.  See
> [Primitives → Reactive Holes](../concepts/primitives.md#reactive-holes).

#### `@component` decorator

The `@component` decorator turns a function into a component.  Each
parameter becomes a **reactive accessor** — a zero-arg callable.

```python
from wybthon import component, h2

@component
def Hello(name="world", greeting="Hello"):
    # Both ``greeting`` and ``name`` are accessors.  Embedding them in
    # the tree creates auto-holes -- text nodes update if the parent
    # passes new values.
    return h2(greeting, ", ", name, "!")
```

* Defaults and type annotations work as you would expect.
* Missing props use the default; extra props not in the signature
  are still tracked but ignored.
* Pass an accessor directly into the tree for a reactive auto-hole.
* Call it (`name()`) for a tracked read.
* Wrap with [`untrack`](../concepts/primitives.md#untrack) for a
  one-shot snapshot (e.g. seeding a signal).

```python
from wybthon import component, create_signal, button, div, p, span, untrack

@component
def Counter(initial=0):
    # ``initial`` is a getter; ``untrack`` reads the seed value once
    # without subscribing.
    count, set_count = create_signal(untrack(initial))
    return div(
        p("Count: ", span(count)),                       # ← reactive hole
        button("+1", on_click=lambda e: set_count(count() + 1)),
        class_="counter",
    )
```

##### Children

`children` is a normal prop — also a reactive accessor.  Most layouts
read it once at setup; wrap with `untrack`:

```python
from wybthon import component, h3, section, untrack

@component
def Card(title="", children=None):
    kids = untrack(children) if callable(children) else children
    if kids is None:
        kids = []
    if not isinstance(kids, list):
        kids = [kids]
    return section(h3(title), *kids, class_="card")
```

For memoized, reactive resolution use the `children()` helper with
`get_props()` — see [Reactivity API](../api/reactivity.md).

##### Direct calls

Calling a component directly with kwargs returns a `VNode`:

```python
Card("child text", title="My Card")  # positional args become children
Counter(initial=5)                    # keyword args become props
```

##### Static or getter — the same call site

A child component never has to care whether the parent passed a
constant or a signal:

```python
@component
def Badge(count=0):
    return p("count: ", count)   # works for static or signal alike

h(Badge, {"count": 7})            # static value
h(Badge, {"count": my_signal})    # signal accessor
```

#### Context

Provide values with `Provider` (signal-backed) and read with
`use_context`:

```python
from wybthon import Provider, component, create_signal, dynamic, h, p, use_context
from wybthon.context import create_context

Theme = create_context("light")

@component
def ThemeLabel():
    # Wrap the read in dynamic() so the text updates when the
    # Provider value changes.
    return p("Theme: ", dynamic(lambda: use_context(Theme)))

@component
def Layout(children=None):
    theme, set_theme = create_signal("dark")
    return h(Provider, {"context": Theme, "value": theme}, ThemeLabel())
```

`Provider`'s `value` accepts both static values and getters; consumers
update reactively without the subtree being re-mounted.

#### Patterns checklist

- Use `@component` for every function component.
- Pass accessors into the tree for reactive auto-holes.
- Use `untrack(prop)` to seed local state from a prop.
- Use `dynamic(getter)` to wrap a derived expression as a reactive hole.
- Pass signals into context's `value` for reactive context updates.
- Use `For`/`Index` for keyed lists; `each=` should be a getter, not a
  plain `list`.
- Use `on_mount` / `on_cleanup` for lifecycle work.

#### Larger examples

1) Composition via children

```python
from wybthon import component, div, h3, p, section, untrack

@component
def Card(title="", children=None):
    kids = untrack(children) if callable(children) else children
    if kids is None:
        kids = []
    if not isinstance(kids, list):
        kids = [kids]
    return section(h3(title), *kids, class_="card")

@component
def Page():
    return div(
        Card(p("Card body via children"), title="Composition"),
    )
```

2) State and derived values (`For` + `dynamic`)

```python
from wybthon import (
    For, button, component, create_memo, create_signal, div, dynamic, li, p, span, ul,
)

@component
def NamesList():
    names, set_names = create_signal([])
    starts_with_a = create_memo(
        lambda: len([n for n in names() if str(n).lower().startswith("a")])
    )

    def make_add(name):
        return lambda _evt: set_names(names() + [name])

    def clear(_evt):
        set_names([])

    return div(
        p(dynamic(lambda: f"Total: {len(names())} | Starts with A: {starts_with_a()}")),
        div(
            button("+ Ada", on_click=make_add("Ada")),
            button("+ Alan", on_click=make_add("Alan")),
            button("Clear", on_click=clear),
        ),
        ul(For(each=names, children=lambda n, _i: li(n))),
    )
```

3) Cleanup and lifecycles

```python
from wybthon import component, create_signal, div, dynamic, on_cleanup, on_mount

@component
def Timer():
    seconds, set_seconds = create_signal(0)

    def start():
        from js import setInterval, clearInterval
        from pyodide.ffi import create_proxy

        proxy = create_proxy(lambda: set_seconds(seconds() + 1))
        tid = setInterval(proxy, 1000)

        on_cleanup(lambda: (clearInterval(tid), proxy.destroy()))

    on_mount(start)

    return div(dynamic(lambda: f"Seconds: {seconds()}"), class_="timer")
```

Putting it together:

```python
from wybthon import component, div, h

@component
def Page():
    return div(
        h(Card, {"title": "State & Derived"}, h(NamesList, {})),
        h(Card, {"title": "Cleanup"}, h(Timer, {})),
    )
```

See the demo app "Patterns" page for a working version of these examples.
