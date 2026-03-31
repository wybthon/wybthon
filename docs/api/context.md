### wybthon.context

::: wybthon.context

#### `create_context(default) -> Context`

Create a new context with a unique ID and a default value.  The default
is returned by `use_context` when no ancestor `Provider` supplies a
value.

#### `use_context(ctx) -> Any`

Read the current value for `ctx` by walking up the **ownership tree**
from `_current_owner`.  Searches each owner's `_context_map` for the
context ID; returns the first match, or `ctx.default` if none is found.

Can be called during a component's setup phase, inside a render
function, or inside an effect — anywhere that runs under a reactive
owner.

#### `Provider(props) -> VNode`

Function component that provides a context value to its subtree.  The
reconciler sets the value on the provider's `_ComponentContext` via
`_set_context`, making it visible to all descendant owners.

Props:

- `context` — a `Context` object created by `create_context`.
- `value` — the value to provide.
- `children` — child VNodes.

Nested providers for the same context shadow outer ones.
