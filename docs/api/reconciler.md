### wybthon.reconciler

::: wybthon.reconciler

#### What's in this module

The reconciler turns VNode trees into batched DOM operations. It never
touches the DOM directly: every mutation is an op against an integer
node id (see [kernel](kernel.md)), and the whole buffer is applied in
one bridge crossing at commit time. Components run once; updates flow
through reactive holes and prop bindings, each patching only its own
region.

What it mounts:

- **Templates.** An [`html`][wybthon.html] template mounts as a `_tpl`
  node: one fused `CLONE` command copies the template's native
  `<template>`, and a generated mount function fills its slots. No
  VNodes exist for the static parts.
- **Element helper trees.** Subtrees built with the
  [element helpers](elements.md) mount through compiled shapes, also
  with one `CLONE` per mount.
- **Regions.** `Show`, `For`, `Repeat`, and `Switch` are native regions
  with no component wrapped around them.
- **Components and holes.** A component body runs once; a hole runs in
  its own render effect.

See [Virtual DOM](../concepts/vdom.md#compiled-templates) for the
details.

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
from wybthon import component, create_signal, html, render


@component
def App():
    title, set_title = create_signal("Hello")
    return html(t"<div><h1>{title}</h1><p>Rendered once; the heading is a hole.</p></div>")


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

Patching only happens where a reactive hole re-renders, or when
`render` runs again into the same container. A hole that returns a
template from the same literal as before patches the mounted instance
slot by slot; a hole that returns the same kind of region pushes the
new condition or source into the mounted one. Components are patched
with new props only in those two places; everywhere else their props
can't change, which is why a constant prop costs nothing.

For everything else, patching matches VNodes by type and key: a different tag or key
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
- [Templates](../concepts/templates.md): how `html` templates compile and mount
- [Concepts: Virtual DOM](../concepts/vdom.md)
- [Concepts: Lifecycle and ownership](../concepts/lifecycle.md)
