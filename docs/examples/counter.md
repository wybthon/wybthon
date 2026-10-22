# Counter

Signals, derived values, a template, and typed props with defaults in one small component.

```python
from wybthon import Props, component, create_memo, create_signal, html, render, untrack


class CounterProps(Props):
    initial: int = 0
    step: int = 1


@component
def Counter(props: CounterProps):
    # ``untrack`` reads ``initial`` once without subscribing, which is
    # exactly what a signal seed needs.
    count, set_count = create_signal(untrack(lambda: props.initial))

    # Memos are cached and glitch-free; ``parity`` recomputes only when
    # ``count`` changes.
    parity = create_memo(lambda: "even" if count() % 2 == 0 else "odd")

    def increment():
        # Writes are staged until the next flush, so use the functional form
        # when the new value depends on the current one.
        set_count(lambda n: n + props.step)

    def reset():
        set_count(props.initial)

    return html(t"""
      <div class="counter">
        <p>Count: {count()}, doubled: {count() * 2}</p>
        <p>{parity()}</p>
        <p>Next: {count()} + {props.step}</p>
        <button onclick={increment}>Increment</button>
        <button onclick={reset}>Reset</button>
      </div>
    """)


render(Counter(initial=5, step=2), "#app")
```

## How it works

- `CounterProps` declares two optional inputs as plain annotations with ordinary defaults. Use [`prop`][wybthon.prop] only when a default needs a factory: `tags: list[str] = prop(default_factory=list)`.
- [`html`][wybthon.html] takes the `t"..."` template string and returns a node. Wybthon's compiler prepares each literal when the module is compiled, and the static markup becomes a native `<template>` that's cloned for every instance. See [Templates](../concepts/templates.md).
- `{count()}`, `{count() * 2}`, `{parity()}`, and `{props.step}` contain a call or an attribute access, so the compiler turns each into a getter. Each one becomes a **reactive hole**: only that text node changes when what it reads changes. Everything else in the markup is static.
- `count() * 2` needs no memo: it's cheap, and the hole recomputes it only when `count` changes. `parity` is a memo to show the other option; a memo is worth it when a derived value is expensive or read in several places.
- `props.step` is a tracked read of the current value. If the parent passes a reactive value, the hole updates.
- `onclick={increment}` registers a delegated click handler. The compiler never wraps an event handler. Attribute names in templates are the HTML names (`class`, `onclick`).
- The component body runs once. There's no re-render to worry about, so closures like `increment` never go stale.
- The handlers take no arguments; a handler may also accept the event. `props.step` and `props.initial` inside a handler are plain reads: event handlers aren't tracking scopes, so they neither subscribe nor warn.

## Calling the component

`@component` returns a [`Component`][wybthon.Component]. Calling it with keyword arguments returns a node:

```python
Counter()  # every prop has a default
Counter(initial=5)
Counter(initial=5, step=10)
```

An unknown or misspelled prop (`Counter(stpe=2)`) is a type error in pyright and mypy, and a `TypeError` at run time in dev mode.

Inside another template, call it in an interpolation to keep that type checking, or use the tag form, which dev mode checks at run time:

```python
html(t"<main>{Counter(initial=5)}</main>")
html(t"<main><{Counter} initial={5} /></main>")
```

Pass a dynamic expression to react to parent state. In a template, the compiler passes the counter a getter, so `props.initial` reads the parent's current value:

```python
from wybthon import create_signal

seed, set_seed = create_signal(0)
html(t"<main>{Counter(initial=seed())}</main>")  # props.initial reflects seed()
```

Because the counter reads `initial` once, untracked, to seed its own signal, later changes to `seed` don't reset the count; "Reset" reads the current seed. That's the intended semantics of a seed. If you want a prop to drive the display directly, place it in the template instead of copying it into a signal. A prop passed as a constant, like `step=2` above, costs nothing to read: it never changes, so nothing subscribes to it.

## Testing it

[`wybthon.testing`][wybthon.testing] renders the counter in plain CPython:

```python
from wybthon.testing import fire, render

with render(Counter(initial=5, step=2)) as screen:
    fire.click(screen.get_by_role("button", name="Increment"))
    assert screen.get_by_text("Count: 7, doubled: 14")
```

## Next steps

- Read [Templates](../concepts/templates.md), [Primitives](../concepts/primitives.md), and [Authoring patterns](../guides/authoring-patterns.md).
- See the [Async fetch example](fetch.md) for async data handling.
- Browse the [`reactivity`][wybthon.reactivity] API for signal helpers.
