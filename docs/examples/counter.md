### Counter

```python
from wybthon import button, component, create_signal, div, on_mount, p, span, untrack

@component
def Counter(initial=0):
    # ``initial`` is a reactive accessor; ``untrack`` reads its
    # current value once without subscribing -- perfect as a
    # signal seed.
    count, set_count = create_signal(untrack(initial))

    on_mount(lambda: print("Counter mounted with initial count:", count()))

    return div(
        p("Count: ", span(count)),                         # ← reactive hole
        button("Increment", on_click=lambda e: set_count(count() + 1)),
        class_="counter",
    )
```

`count` is a zero-arg accessor returned by `create_signal`.  When you
embed it in the VNode tree the reconciler wraps it in its own effect —
only that text node updates when the signal changes.  See
[Primitives → Reactive Holes](../concepts/primitives.md#reactive-holes).

#### Direct call form (no `h`)

`@component` lets you call the component directly with kwargs:

```python
Counter(initial=5)              # → h(Counter, {"initial": 5})
```

Pass a getter to react to parent state changes — the child code does
not change:

```python
seed, set_seed = create_signal(0)
Counter(initial=seed)           # ``initial()`` will reflect ``seed()``
```

## Next steps

- Read [Primitives](../concepts/primitives.md) and [Authoring Patterns](../guides/authoring-patterns.md).
- See the [Async fetch example](fetch.md) for resource handling.
- Browse the [`reactivity`][wybthon.reactivity] API for signal helpers.
