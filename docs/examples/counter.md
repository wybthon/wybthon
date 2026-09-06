# Counter

Signals, a derived value, holes, and a typed prop default in one small component.

```python
from wybthon import Prop, button, component, create_memo, create_signal, div, p, prop, render, span


@component
def Counter(initial: Prop[int] = prop(0), step: Prop[int] = prop(1)):
    # ``initial`` is a Prop accessor. ``.peek()`` reads it once without
    # subscribing, which is exactly what a signal seed needs.
    count, set_count = create_signal(initial.peek())

    # Memos are lazy and glitch-free; ``doubled`` recomputes only when read
    # after ``count`` changed.
    doubled = create_memo(lambda: count() * 2)

    def increment(e):
        # Writes are staged until the next flush, so use the functional form
        # when the new value depends on the current one.
        set_count(lambda n: n + step())

    def reset(e):
        set_count(initial.peek())

    return div(
        p("Count: ", span(count), ", doubled: ", span(doubled)),
        p(lambda: "even" if count() % 2 == 0 else "odd"),
        button("Increment", on_click=increment),
        button("Reset", on_click=reset),
        class_="counter",
    )


render(Counter(initial=5, step=2), "#app")
```

## How it works

- `count` and `doubled` are accessors. Placing an accessor in the tree creates a **reactive hole**: the reconciler runs it inside its own render effect and patches only that text node when a dependency changes.
- `lambda: "even" if count() % 2 == 0 else "odd"` is also a hole. Any zero-argument callable in a child position is treated the same way as an accessor.
- The component body runs once. There's no re-render to worry about, so closures like `increment` never go stale.
- `step()` inside the event handler is a plain read; event handlers aren't tracking scopes, so it neither subscribes nor warns.

## Calling the component

`@component` returns a [`Component`][wybthon.Component]. Calling it with keyword arguments returns a VNode:

```python
Counter(initial=5)            # keyword args become props
Counter(initial=5, step=10)
```

Pass an accessor to react to parent state without changing the child:

```python
from wybthon import create_signal

seed, set_seed = create_signal(0)
Counter(initial=seed)          # ``initial()`` reflects ``seed()``
```

Because the counter only peeks at `initial` to seed its own signal, later changes to `seed` don't reset the count. That's the intended semantics of a seed; if you want a prop to drive the display directly, place the prop in the tree instead of copying it into a signal.

## Next steps

- Read [Primitives](../concepts/primitives.md) and [Authoring patterns](../guides/authoring-patterns.md).
- See the [Async fetch example](fetch.md) for async data handling.
- Browse the [`reactivity`][wybthon.reactivity] API for signal helpers.
