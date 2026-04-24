### Context

Provide and consume values across the component tree without prop
drilling.

```python
from wybthon import component, dynamic, h, p
from wybthon.context import create_context, Provider, use_context

Theme = create_context("light")

@component
def Label():
    return p("Theme: ", dynamic(lambda: use_context(Theme)))

view = h(Provider, {"context": Theme, "value": "dark"}, h(Label, {}))
```

#### Reactive `value`

`Provider`'s `value` prop is **signal-backed**: passing a getter (or a
signal accessor) makes the provided value reactive.  Consumers that
read `use_context` inside a reactive hole will update automatically
when the value changes, without a subtree re-mount.

```python
from wybthon import component, create_signal, dynamic, h, p, use_context, Provider

@component
def App():
    theme, set_theme = create_signal("dark")
    return h(Provider, {"context": Theme, "value": theme},  # ← getter
             h(Label, {}))

@component
def Label():
    # Wrap in dynamic so the text node updates when ``theme`` flips.
    return p(dynamic(lambda: f"Theme: {use_context(Theme)}"))
```

If you only need a static value, pass it as-is; the Provider handles
both shapes uniformly.

#### How it works: the ownership tree

Context values are stored directly on the **reactive ownership tree**,
not on a separate render-time stack.  When a `Provider` component
mounts, the reconciler creates a per-context signal on that component's
`_ComponentContext` owner.  Consumers read the signal via
`use_context`, so they participate in normal reactive tracking.

```
Root Owner
└── ComponentContext (App)
    └── ComponentContext (Provider)   ← _context_map = {Theme.id: signal("dark")}
        └── ComponentContext (Label)
            └── render effect
                ← use_context(Theme) walks up, reads the signal,
                  and tracks it for future updates.
```

This ownership-based lookup means context is available at any point
during a component's lifecycle (setup phase, render function, or
inside effects) as long as the code runs under an owner that is a
descendant of the provider.

#### Provider scoping

Each `Provider` sets its value on its own component context.  Nested
providers for the same context naturally shadow outer ones because the
ownership-tree walk finds the nearest ancestor first:

```python
h(Provider, {"context": Theme, "value": "light"},
    h(Provider, {"context": Theme, "value": "dark"},
        h(Label, {})),  # sees "dark"
    h(Label, {}),       # sees "light"
)
```

#### Performance

Context lookup is a simple parent-pointer walk: no dict copies, no
stack manipulation.  The cost is proportional to the depth between the
consumer and the nearest provider, which is typically small.  When the
`Provider` value is a getter, an internal effect mirrors it into the
context signal so consumers update reactively without the `Provider`
itself re-rendering.

## Next steps

- See the [`context`][wybthon.context] API for `Context`, `Provider`, and `use_context`.
- Read [Lifecycle and Ownership](lifecycle.md) for how the ownership tree works.
- Explore [Stores](stores.md) when you need a richer reactive container.
