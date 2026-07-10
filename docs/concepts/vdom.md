### Virtual DOM

The VDOM is represented by `VNode` and created via `h(tag, props, *children)`.

- `tag`: string (DOM node) or callable (component)
- `props`: attributes, event handlers, special props (`key`, `ref`),
  or **getter callables** that become reactive bindings
- `children`: strings, `VNode`s, or **getter callables** that become
  reactive holes

```python
from wybthon import h

view = h("div", {"class": "app"},
          h("h1", {}, "Hello"),
          h("p", {}, "Welcome"))
```

Rendering is done with `render(view, container)`.

#### Reactive holes (fine-grained updates)

A zero-arg callable placed inside a VNode tree becomes a **reactive
hole**: the reconciler wraps it in its own effect, so only the hole
(and not the surrounding component) re-runs when its dependencies
change.  This is how Wybthon achieves SolidJS-style fine-grained
updates while keeping the VDOM as a batching layer.

```python
from wybthon import create_signal, dynamic, h

count, set_count = create_signal(0)

view = h("p", {"class": lambda: f"counter {('odd' if count() % 2 else 'even')}"},
         "Count: ",
         count,                              # text hole (signal accessor)
         dynamic(lambda: f" (×2={count()*2})"))  # text hole (derived expression)
```

Holes are also recognised on prop values (except `on_*` event handlers
and `ref`).  Each prop has its own effect, so unrelated reactive
attributes update independently.  See the [Reactive Holes section in
Primitives](primitives.md#reactive-holes) for the full mental model.

#### The batched rendering kernel

Under Pyodide, every DOM call crosses the Python-to-JS bridge, so
rendering cost is dominated by FFI round trips rather than the DOM work
itself. Wybthon therefore never calls DOM APIs directly. The reconciler
and prop appliers *emit* compact operations (create, insert, set-text,
set-attr, listen, and so on) against integer node ids into a command
buffer. At each commit point (end of a `render`, end of an effect
flush, end of an event handler) the whole buffer is serialized once and
handed to a small JavaScript kernel that applies every operation
natively. A mount of a 1,000-row table becomes one bridge crossing
instead of tens of thousands. See `wybthon.kernel` for the wire
protocol.

#### Template-based mounting

On top of the command buffer, the reconciler serializes the **static
skeleton** of a host-element subtree into one HTML string with text
content hoisted out, registers it with the kernel once, and mounts each
occurrence with a single *clone* op. The kernel clones the pre-parsed
`<template>` and assigns a dense block of node ids in a deterministic
pre-order, so Python knows every node's id without reading anything
back. Text, reactive bindings, event handlers, and dynamic children are
then wired by id in the same batch.

Because text is hoisted, structurally-identical subtrees (like list
rows) share one template: the browser parses the skeleton once and
clones it per row, exactly like SolidJS's compiled templates.

This happens automatically; subtrees that can't be expressed faithfully
as HTML (raw-text elements, adjacent text nodes, and so on) fall back
to per-node ops, still batched in the same commit. See the
[`template`][wybthon.template] API page for details.

#### Architecture

The VDOM implementation is split into focused modules:

- **`vnode`**: the `VNode` data structure, `h()`, `Fragment`, and `dynamic()` (browser-agnostic). `Fragment` doesn't insert a wrapper element; reconciliation uses comment-node boundaries so the DOM tree stays free of extra spans and CSS selectors stay predictable.
- **`kernel`**: the batched command buffer, the embedded JS kernel that applies ops natively, and the reference Python interpreter used by tests.
- **`template`**: the template-based mounting fast path (HTML serialization plus binding wiring).
- **`reconciler`**: the mount/patch/unmount diffing engine (emits ops).
- **`props`**: DOM property application and diffing (styles, events, datasets), also op-based.
- **`error_boundary`**: the `ErrorBoundary` component.
- **`suspense`**: the `Suspense` component.
- **`portal`**: the `create_portal()` function.

The most common names are available at the top-level `wybthon` package.

#### Keyed diffing

- Provide `key` on children of dynamic lists: `h("li", {"key": item.id}, ...)`.
- Keys allow Wybthon to match, reorder, insert, and remove children with minimal DOM changes while preserving element identity and state.
- The reconciler first matches children by key, then falls back to type-matching for unkeyed nodes.

#### Error reporting

In development mode (`DEV_MODE = True`, the default), rendering errors include
the component name and a full traceback printed to stderr. This makes it easy
to locate problems in component trees. Set `set_dev_mode(False)` for production
to suppress verbose tracebacks.

## Next steps

- See [Primitives](primitives.md) for the reactive hole mental model.
- Read [Lifecycle and Ownership](lifecycle.md) for mount/unmount semantics.
- Browse the [`reconciler`][wybthon.reconciler] and [`template`][wybthon.template] APIs.
