# Virtual DOM

Wybthon keeps a small virtual DOM as a rendering implementation detail.
This page explains why it exists, how reactive holes and the reconciler
use it, and how DOM operations reach the browser.

## Why a VDOM in a fine-grained framework?

SolidJS compiles JSX ahead of time, splitting each template into a
static skeleton and the expressions that change. Python has no such
compiler, and in Pyodide every DOM call crosses the Python-to-JS bridge,
which dominates rendering cost. So Wybthon does the split at runtime:

- A component returns a [`VNode`][wybthon.VNode] tree once.
- Reactive expressions inside it become **holes**, each with its own render effect.
- When a hole re-evaluates, the **reconciler** diffs the hole's old and new subtree and emits compact operations against integer node ids.
- All operations from one flush are handed to a small **JavaScript kernel** in one bridge crossing.

The reactive model is Solid's. The VDOM is the batching layer that makes
it fast under Pyodide; it never diffs whole components, only the region
under a hole.

## Building trees

[`h(tag, props, *children)`][wybthon.h] builds a VNode. The helpers in
`wybthon.html` (and `wybthon.svg`) wrap it with a friendlier signature:
`div(*children, **props)`.

```python
from wybthon import Fragment, h
from wybthon.html import div, h1, p

view = h("div", {"class": "app"}, h("h1", {}, "Hello"), h("p", {}, "Welcome"))
same = div(h1("Hello"), p("Welcome"), class_="app")
grouped = Fragment(h1("Title"), p("Body"))
```

- `tag` is an HTML tag, an SVG tag, or a component.
- Props are attributes, DOM properties, event handlers, `ref`, `key`, or reactive bindings.
- Children are strings, numbers, VNodes, lists (flattened), `None` (dropped), or reactive expressions (holes).

Prop names are Pythonic: `class_` becomes `class`, `html_for` becomes
`for`, and other underscores become hyphens (`aria_label`,
`data_testid`). `True` sets a boolean attribute and `False` or `None`
removes it. `value` and `checked` are written as DOM properties. `class_`
accepts a string, a list, or a `{name: bool}` dict; `style` accepts a
string or a dict with snake- or kebab-case keys. Use
[`element("my-tag")`][wybthon.element] for custom elements.

## Reactive holes

A zero-arg callable or accessor in a child position becomes a hole; so
does one used as a prop value (except event handlers and `ref`). Each
hole is a render effect. Use [`hole`][wybthon.hole] to create one
explicitly when you need a `key`.

```python
from wybthon import create_signal, hole
from wybthon.html import p

count, set_count = create_signal(0)

view = p(
    "Count: ",
    count,                                  # text hole (accessor)
    lambda: f" (x2={count() * 2})",         # text hole (expression)
    hole(lambda: "!" * count(), key="bang"),  # explicit hole with a key
    class_=lambda: "odd" if count() % 2 else "even",   # reactive prop binding
)
```

A hole's expression may return a string, a `VNode`, a list (mounted as
a fragment between the hole's markers), `None`, or another accessor.
Holes are ownership scopes: components mounted inside one survive its
re-evaluations while the reconciler can patch them in place, and
[`on_cleanup`][wybthon.on_cleanup] inside the expression runs before
each re-run.

Each reactive prop has its own render effect, so unrelated attributes on
the same element update independently.

## The reconciler

When a hole re-evaluates, [`patch`](../api/reconciler.md) diffs the old
subtree against the new one:

- Same VNode instance (for example a cached `For` row): skipped.
- Same tag and key: patched in place. Props are diffed, text is updated, and children are reconciled.
- Different tag or key: the old subtree is unmounted and the new one mounted at the same position.

Children are matched in three passes: by identity, by `key`, then by
type in document order. DOM moves are minimized with a
longest-increasing-subsequence pass, so a reorder emits only the
inserts that are strictly necessary.

### Keys

Give siblings a stable `key` when their order can change and they carry
state (form inputs, components with local signals). A component
re-rendered with a different key remounts with fresh state:

```python
div(lambda: Editor(user_id=current_id(), key=current_id()))
```

Prefer [`For`][wybthon.For] for lists: it caches each row's VNode and
scope, so rows are moved rather than re-diffed at all.

## The batched rendering kernel

Nothing in the renderer touches the DOM directly. The reconciler and
prop appliers *emit* operations such as create, insert, set-text,
set-attr, and listen against integer node ids into a command buffer.
At each commit point (the end of `render`, the DOM phase of every flush)
the buffer is serialized once and handed to the JS kernel, which applies
every operation natively and keeps an `id -> Node` registry. A mount of
a thousand-row table is one bridge crossing instead of tens of
thousands. The [`kernel`](../api/kernel.md) page documents the wire
protocol.

The same protocol drives a pure-Python backend
(`kernel.PythonBackend`) that applies the ops to an in-memory stub
document. Unit tests and the stubbed benchmark run against it, so both
exercise exactly what the browser sees. See the
[Testing guide](../guides/testing.md).

## Template-based mounting

On top of the command buffer, the reconciler serializes the **static
skeleton** of an element subtree into one HTML string, registers it
with the kernel once, and mounts each occurrence with a single clone op.
The kernel clones the pre-parsed `<template>` and assigns a dense block
of node ids in pre-order, so Python knows every node's id without
reading anything back. Text, reactive bindings, event handlers, refs,
and dynamic children are then wired by id in the same batch.

Static text is hoisted out of the HTML and applied afterwards, so
structurally identical subtrees (list rows that differ only in their
text) share one template. The browser parses the skeleton once and
clones it per row, exactly like SolidJS's compiled templates. Plans are
cached per shape, so the serialization runs once per distinct subtree
structure.

Subtrees the HTML parser would mangle (adjacent text nodes, raw-text
elements, implied `<tbody>`, and similar) fall back to per-node ops,
still batched in the same commit. See the
[`template`](../api/template.md) page.

## Event delegation

Handlers such as `on_click` don't attach native listeners per element.
Registering one is a `LISTEN` op in the same buffer, and the kernel
installs one native listener per event type on each **render root**
(the container passed to `render`). When an event fires, the kernel
walks the ancestor chain natively and calls into Python once per node
that registered a handler, with a small JSON payload. See
[Events](events.md).

## `render` and `Root`

[`render(vnode, container)`][wybthon.render] mounts a tree into an
[`Element`][wybthon.Element], a CSS selector, or a kernel node id,
commits the buffer, registers the container as an event root, and
returns a [`Root`][wybthon.Root]. Rendering into the same container
again patches the existing tree in place.

```python
from wybthon import render
from wybthon.html import h1

root = render(h1("Hello, world!"), "#app")
root.container   # the container Element
root.vnode       # the mounted root VNode
root.dispose()   # unmount, dispose every scope, unregister the event root
```

## Architecture

- **`vnode`**: `VNode`, `h`, `Fragment`, `hole`, and child normalization (no browser dependency).
- **`html`** and **`svg`**: tag helpers; SVG elements propagate their namespace to children.
- **`props`**: attribute, property, class, style, dataset, ref, and reactive-binding application, all op-based.
- **`template`**: the static-skeleton fast path.
- **`reconciler`**: mount, patch, unmount, `render`, and `Root`.
- **`kernel`**: the command buffer, the embedded JS kernel, and the Python reference backend.
- **`events`**: the Python half of delegation and [`DomEvent`][wybthon.DomEvent].

The common names are re-exported from the top-level `wybthon` package.

## Error reporting

In dev mode, render errors are logged with the component name and a
full traceback. An [`Errored`][wybthon.Errored] boundary above the
failing subtree catches the error and shows a fallback instead. Call
[`set_dev_mode(False)`][wybthon.set_dev_mode] in production to suppress
tracebacks.

## Next steps

- See [Primitives](primitives.md#reactive-holes) for the hole mental model.
- Read [Lifecycle and ownership](lifecycle.md) for mount and unmount semantics.
- Browse the [`reconciler`](../api/reconciler.md), [`template`](../api/template.md), and [`kernel`](../api/kernel.md) API pages.
