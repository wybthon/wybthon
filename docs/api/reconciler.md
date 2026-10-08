### wybthon.reconciler

::: wybthon.reconciler

#### What's in this module

The reconciler turns VNode trees into batched DOM operations. It never
touches the DOM directly: every mutation is an op against an integer
node id (see [kernel](kernel.md)), and the whole buffer is applied in
one bridge crossing at commit time. Components run once; updates flow
through reactive holes and prop bindings, each patching only its own
region. Element subtrees mount through compiled shapes: a generated
mount function per shape and one fused `CLONE` command per mount (see
[Virtual DOM](../concepts/vdom.md#compiled-mounting)).

| Name | Description |
| --- | --- |
| [`render`][wybthon.render] | Mount a tree into a container (`Element`, CSS selector, or node id) and return a `Root`. Rendering into the same container again patches in place. |
| [`hydrate`][wybthon.hydrate] | Adopt server-rendered HTML under a container instead of creating it; see [Server rendering](../concepts/server-rendering.md). |
| [`Root`][wybthon.Root] | Handle returned by `render` and `hydrate`; `.container`, `.vnode`, `.node_id`, and `.dispose()`. |
| [`mount`][wybthon.reconciler.mount] | Lower level: emit ops mounting a VNode under a parent id, optionally before an anchor. |
| [`patch`][wybthon.reconciler.patch] | Lower level: diff an old VNode against a new one and emit minimal ops. |
| [`unmount`][wybthon.reconciler.unmount] | Lower level: dispose a VNode's scopes and effects, then remove its DOM with one native `DISPOSE` or `DISPOSE_RANGE` command. |

`render`, `hydrate`, and `Root` are re-exported from `wybthon`; `mount`, `patch`,
and `unmount` are for control-flow primitives and tests.

```python
from wybthon import component, create_signal, div, h1, p, render


@component
def App():
    title, set_title = create_signal("Hello")
    return div(h1(title), p("Rendered once; the heading is a hole."))


root = render(App(), "#app")
# Tear everything down: unmounts the tree, disposes every reactive
# scope, and stops event delegation on the container.
root.dispose()
```

What happens inside `render`:

1. The container is resolved to a kernel node id and registered as an
   event-delegation root (`ROOT` op).
2. The tree mounts under a fresh [`Owner`][wybthon.Owner]; component
   bodies run once, and holes and reactive props create render effects.
3. `flush()` commits staged writes, runs effects, and sends the op
   buffer across the bridge once.

Patching matches VNodes by type and key: a different tag or key
unmounts and remounts at the same position (so `Leaf(key=user_id())`
restarts its state when the id changes). Keyed children use an
identity, key, then type match with a longest-increasing-subsequence
move pass to keep DOM moves minimal. When a keyed list reuses none of
its rows, the new rows mount as one splice and the old ones are removed
with a single `DISPOSE_RANGE`. Errors raised during mount or in a hole
route to the nearest [`Errored`][wybthon.Errored] boundary.

#### See also

- [Kernel](kernel.md): the op protocol and backends
- [VNode](vnode.md): the data structure being diffed
- [Concepts: Virtual DOM](../concepts/vdom.md)
- [Concepts: Lifecycle and ownership](../concepts/lifecycle.md)
