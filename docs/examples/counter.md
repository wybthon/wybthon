# Counter

Signals, derived values, a template, and typed props with defaults in one small component.

```python
from wybthon import Prop, Props, component, create_memo, create_signal, html, prop, render


class CounterProps(Props):
    initial: Prop[int] = prop(default=0)
    step: Prop[int] = prop(default=1)


@component
def Counter(props: CounterProps):
    # ``props.initial`` is an accessor. ``.peek()`` reads it once without
    # subscribing, which is exactly what a signal seed needs.
    count, set_count = create_signal(props.initial.peek())

    # Memos are cached and glitch-free; ``doubled`` recomputes only when
    # ``count`` changes.
    doubled = create_memo(lambda: count() * 2)
    parity = create_memo(lambda: "even" if count() % 2 == 0 else "odd")

    def increment():
        # Writes are staged until the next flush, so use the functional form
        # when the new value depends on the current one.
        set_count(lambda n: n + props.step())

    def reset():
        set_count(props.initial.peek())

    return html(t"""
      <div class="counter">
        <p>Count: {count}, doubled: {doubled}</p>
        <p>{parity}</p>
        <p>Next: {count} + {props.step}</p>
        <button onclick={increment}>Increment</button>
        <button onclick={reset}>Reset</button>
      </div>
    """)


render(Counter(initial=5, step=2), "#app")
```

## How it works

- `CounterProps` declares two optional inputs. `Prop[int]` makes each reactive, and `prop(default=...)` supplies the default.
- [`html`][wybthon.html] takes the `t"..."` template string and returns a node. The literal is compiled once, the first time it runs, into a native `<template>` that's cloned for every instance. See [Templates](../concepts/templates.md).
- `count`, `doubled`, `parity`, and `props.step` are accessors. Placing an accessor in a template creates a **reactive hole**: it gets its own render effect, and only that text node changes when its dependencies do. Everything else in the markup is static.
- `parity` could also be written inline, as `{(lambda: "even" if count() % 2 == 0 else "odd")}`. Python doesn't allow a bare `lambda` inside `{...}`, so an inline one needs the parentheses. A named memo or function usually reads better.
- `onclick={increment}` registers a delegated click handler. Attribute names in templates are the HTML names (`class`, `onclick`), not the helpers' Python names (`class_`, `on_click`).
- The component body runs once. There's no re-render to worry about, so closures like `increment` never go stale.
- The handlers take no arguments; a handler may also accept the event. `props.step()` inside a handler is a plain read: event handlers aren't tracking scopes, so it neither subscribes nor warns.

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

Pass an accessor to react to parent state without changing the child:

```python
from wybthon import create_signal

seed, set_seed = create_signal(0)
Counter(initial=seed)  # ``props.initial()`` reflects ``seed()``
```

Because the counter only peeks at `initial` to seed its own signal, later changes to `seed` don't reset the count. That's the intended semantics of a seed; if you want a prop to drive the display directly, place the prop in the template instead of copying it into a signal. A prop passed as a constant, like `step=2` here, costs nothing to read: it never changes, so nothing subscribes to it.

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
