### Context

Provide and consume values across the component tree without prop
drilling.

```python
from wybthon import h
from wybthon.context import create_context, Provider, use_context

Theme = create_context("light")

def Label(props):
    theme = use_context(Theme)
    return h("span", {}, f"Theme: {theme}")

view = h(Provider, {"context": Theme, "value": "dark", "children": [h(Label, {})]})
```

#### How it works: the ownership tree

Context values are stored directly on the **reactive ownership tree**,
not on a separate render-time stack.  When a `Provider` component
mounts, the reconciler calls `_set_context(ctx_id, value)` on that
component's `_ComponentContext` owner.  This writes the value into the
owner's `_context_map`.

When `use_context(ctx)` is called, it walks **up** the owner chain
(`_current_owner → parent → parent → ...`) looking for the first owner
whose `_context_map` contains the context ID.  If none is found, the
context's default value is returned.

```
Root Owner
└── ComponentContext (App)
    └── ComponentContext (Provider)   ← _context_map = {Theme.id: "dark"}
        └── ComponentContext (Label)
            └── render effect
                ← use_context(Theme) walks up and finds "dark"
```

This ownership-based lookup means context is available at any point
during a component's lifecycle — setup phase, render function, or inside
effects — as long as the code runs under an owner that is a descendant
of the provider.

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

Context lookup is a simple parent-pointer walk — no dict copies, no
stack manipulation.  The cost is proportional to the depth between the
consumer and the nearest provider, which is typically small.
