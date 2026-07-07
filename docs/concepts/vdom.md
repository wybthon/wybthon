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

#### Template-based mounting

Under Pyodide, every DOM call crosses the Python-to-JS bridge, so mount
cost is dominated by FFI round trips rather than the DOM work itself.
To amortize that cost, the reconciler serializes the **static parts** of
a host-element subtree into one HTML string, parses it through a single
`<template>` element, and then wires reactive bindings, event handlers,
and dynamic children onto the cloned nodes in one pass. Mounting a
subtree of N static nodes costs roughly one FFI call instead of N.

This happens automatically; subtrees that can't be expressed faithfully
as HTML (form control `value`/`checked`, raw-text elements, and so on)
fall back to node-by-node mounting with identical behavior. See the
[`template`][wybthon.template] API page for details.

#### Architecture

The VDOM implementation is split into focused modules:

- **`vnode`**: the `VNode` data structure, `h()`, `Fragment`, and `dynamic()` (browser-agnostic). `Fragment` doesn't insert a wrapper element; reconciliation uses comment-node boundaries so the DOM tree stays free of extra spans and CSS selectors stay predictable.
- **`template`**: the template-based mounting fast path (HTML serialization plus binding wiring).
- **`reconciler`**: the mount/patch/unmount diffing engine.
- **`props`**: DOM property application and diffing (styles, events, datasets).
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
