# Counter

Signals, a derived value, holes, t-strings, and typed props with defaults in one small component.

```python
from wybthon import Prop, Props, button, component, create_memo, create_signal, div, p, prop, render, span


class CounterProps(Props):
    initial: Prop[int] = prop(default=0)
    step: Prop[int] = prop(default=1)


@component
def Counter(props: CounterProps):
    # ``props.initial`` is an accessor. ``.peek()`` reads it once without
    # subscribing, which is exactly what a signal seed needs.
    count, set_count = create_signal(props.initial.peek())

    # Memos are lazy and glitch-free; ``doubled`` recomputes only when read
    # after ``count`` changed.
    doubled = create_memo(lambda: count() * 2)

    def increment():
        # Writes are staged until the next flush, so use the functional form
        # when the new value depends on the current one.
        set_count(lambda n: n + props.step())

    def reset():
        set_count(props.initial.peek())

    return div(
        p("Count: ", span(count), ", doubled: ", span(doubled)),
        p(lambda: "even" if count() % 2 == 0 else "odd"),
        p(t"Next: {count} + {props.step}"),
        button("Increment", on_click=increment),
        button("Reset", on_click=reset),
        class_="counter",
    )


render(Counter(initial=5, step=2), "#app")
```

## How it works

- `CounterProps` declares two optional inputs. `Prop[int]` makes each reactive, and `prop(default=...)` supplies the default.
- `count` and `doubled` are accessors. Placing an accessor in the tree creates a **reactive hole**: the reconciler runs it inside its own render effect and patches only that text node when a dependency changes.
- `lambda: "even" if count() % 2 == 0 else "odd"` is also a hole. Any zero-argument callable in a child position is treated the same way as an accessor.
- `t"Next: {count} + {props.step}"` is a t-string. Its reactive interpolations are read inside one binding, so the whole line updates together.
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

Pass an accessor to react to parent state without changing the child:

```python
from wybthon import create_signal

seed, set_seed = create_signal(0)
Counter(initial=seed)  # ``props.initial()`` reflects ``seed()``
```

Because the counter only peeks at `initial` to seed its own signal, later changes to `seed` don't reset the count. That's the intended semantics of a seed; if you want a prop to drive the display directly, place the prop in the tree instead of copying it into a signal.

## Testing it

[`wybthon.testing`][wybthon.testing] renders the counter in plain CPython:

```python
from wybthon.testing import fire, render

with render(Counter(initial=5, step=2)) as screen:
    fire.click(screen.get_by_role("button", name="Increment"))
    assert screen.get_by_text("Count: 7, doubled: 14")
```

## Next steps

- Read [Primitives](../concepts/primitives.md) and [Authoring patterns](../guides/authoring-patterns.md).
- See the [Async fetch example](fetch.md) for async data handling.
- Browse the [`reactivity`][wybthon.reactivity] API for signal helpers.
