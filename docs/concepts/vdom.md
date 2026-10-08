# Virtual DOM

Wybthon keeps a small virtual DOM as a rendering implementation detail.
This page explains why it exists, how reactive holes and the reconciler
use it, how repeated subtrees mount from compiled shapes, and how DOM
operations reach the browser.

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
under a hole. Removing it in favor of direct DOM calls would put a
bridge crossing behind every node, which is exactly the cost the batch
avoids. Profiling shows the remaining cost is Python bookkeeping around
the VDOM, not the VDOM itself, so engine v2 attacks that bookkeeping
with compiled mounting (see [RFC 0002](../rfcs/0002-engine-v2.md)).

## Building trees

[`h(tag, props, *children)`][wybthon.h] builds a VNode. The helpers in
`wybthon.html` (and `wybthon.svg`) wrap it with a friendlier signature:
`div(*children, **props)`. Every helper also accepts children with item
syntax, which reads well when the props are long.

```python
from wybthon import Fragment, div, h, h1, p

view = h("div", {"class": "app"}, h("h1", {}, "Hello"), h("p", {}, "Welcome"))
same = div(h1("Hello"), p("Welcome"), class_="app")
items = div(class_="app")[h1("Hello"), p("Welcome")]
grouped = Fragment(h1("Title"), p("Body"))
```

- `tag` is an HTML tag, an SVG tag, or a component.
- Props are attributes, DOM properties, event handlers, `ref`, `key`, or reactive bindings.
- Children are strings, numbers, VNodes, lists (flattened), `None` (dropped), template strings, or reactive expressions (holes).

Prop names are Pythonic. The helpers store them as written
(`div(class_="x").props == {"class_": "x"}`), and the prop applier maps
them when it writes the attribute: `class_` becomes `class`, `html_for`
becomes `for`, and other underscores become hyphens (`aria_label`,
`data_testid`). `True` sets a boolean attribute and `False` or `None`
removes it. `value` and `checked` are written as DOM properties. `class_`
accepts a string, a list, or a `{name: bool}` dict; `style` accepts a
string or a dict with snake- or kebab-case keys. Use
[`element("my-tag")`][wybthon.element] for custom elements.

## Reactive holes

A zero-arg callable or accessor in a child position becomes a hole; so
does one used as a prop value (except event handlers and `ref`). Each
hole is a render effect. A [PEP 750](https://peps.python.org/pep-0750/)
template string that interpolates an accessor is one hole for the whole
string. Use [`hole`][wybthon.hole] to create one explicitly when you
need a `key`.

```python
from wybthon import create_signal, hole, p

count, set_count = create_signal(0)

view = p(
    t"Count: {count}",  # one text hole for the whole string
    lambda: f" (x2={count() * 2})",  # text hole (expression)
    hole(lambda: "!" * count(), key="bang"),  # explicit hole with a key
    class_=lambda: "odd" if count() % 2 else "even",  # reactive prop binding
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
state (form inputs, components with local signals). Every component
accepts `key=`. A component re-rendered with a different key remounts
with fresh state:

```python
div(lambda: Editor(user_id=current_id(), key=current_id()))
```

Prefer [`For`][wybthon.For] for lists: it caches each row's VNode and
scope, so rows are moved rather than re-diffed at all.

## The batched rendering kernel

Nothing in the renderer touches the DOM directly. The reconciler and
prop appliers *emit* operations such as clone, insert, set-text, and
set-attr against integer node ids into a command buffer. At each commit
point (the end of `render`, the DOM phase of every flush) the buffer is
serialized once and handed to the JS kernel, which applies every
operation natively and keeps an `id -> Node` registry. A mount of a
thousand-row table is one bridge crossing instead of tens of thousands.
The [`kernel`](../api/kernel.md) page documents the wire protocol.

The same protocol drives a pure-Python backend
(`kernel.PythonBackend`) that applies the ops to an in-memory stub
document. Unit tests, [`wybthon.testing`](../api/testing.md), and the
stubbed benchmark run against it, so all of them exercise exactly what
the browser sees. See the [Testing guide](../guides/testing.md).

## Compiled mounting

On top of the command buffer, element subtrees mount from compiled
**shapes**. This is the runtime analogue of SolidJS's compiled
templates, and it lives in the private `wybthon._template` module.

### Shapes

The first mount of an element subtree walks it once and records its
shape:

- the serialized skeleton HTML, validated so the browser's parser
  reproduces it node for node;
- the pre-order node count;
- each text slot's offset;
- each binding's offset and kind (event, reactive prop, static prop, or ref);
- each dynamic child's offset (a hole, or a nested component, fragment, or list).

Static text is hoisted out of the HTML and filled in per mount, so
subtrees that differ only in text (list rows) share one skeleton. The
skeleton is registered with the kernel once (`REGISTER_TPL`), which
parses it into a `<template>` prototype. Shapes are cached by structure,
so the walk runs once per distinct subtree shape.

### Generated mount functions

A shape gets a generated Python function that mounts any tree of that
shape in straight-line code. It:

1. guards the instance's structure, without allocating, and falls back to the generic path if a guard fails;
2. allocates a dense block of node ids;
3. appends one fused `CLONE` command;
4. wires bindings by offset;
5. mounts dynamic children at their placeholders;
6. records the shape and first id on the root VNode.

The generated source contains only framework names and integer offsets.
Tags, prop names, and static values live in a constants table.

### One fused command per mount

`CLONE` clones the prototype, registers its nodes in pre-order, fills
its text slots, marks its delegated listeners, and inserts the clone
before an anchor, all in one command:
`[CLONE, first_id, tpl_id, parent_id, anchor_id, *texts]`. Python and
the kernel count nodes in the same pre-order, so every node's id is
known without reading anything back. A row of the js-framework-benchmark
table costs two commands (`CLONE` plus `HOLE_TEXT` for its label)
instead of seven.

### Template-declared listeners

The template registration lists the delegated event types at each
offset. Cloning a row marks those listeners natively, so mounting a row
with two handlers sends no `LISTEN` commands. Python stores the handlers
in one table keyed by node id, with the event key derived once per
shape.

### Text-anchored holes

A hole needs a placeholder in the skeleton. When its neighbors aren't
text, the placeholder is a one-space text node rather than a comment,
so a hole that produces text becomes a plain `nodeValue` write
(`HOLE_TEXT`) instead of a replacement.

### Lazy node ids

A template-mounted subtree keeps its VNodes, but only the root (and the
dynamic children) get their `el` assigned at mount. Static descendants
get ids the first time the reconciler needs them: when a hole patches
the subtree, or when a dynamic child needs an anchor. List rows and
component output are never patched that way, so they skip the work
entirely.

### When the fast path is skipped

Subtrees the HTML parser would rewrite fall back to per-node commands,
still batched in the same commit. That includes single-node subtrees,
adjacent or empty text, raw-text elements such as `<script>` and
`<textarea>`, SVG and MathML subtrees (mounted with
`CREATE_ELEMENT_NS`), and nestings the parser rewrites (bare text inside
`<table>`, an implied `<tbody>`, an auto-closed `<p>`). Backends that
can't parse HTML skip templates too. The fallback is purely a
performance difference; behavior is identical.

## Teardown

Unmounting doesn't visit every node in Python. `DISPOSE_RANGE` removes a
contiguous range of siblings and releases every registered node inside
it, and `DISPOSE` does the same for one node's subtree; the kernel walks
the removed nodes natively. Python-side registrations (handlers,
reactive bindings, refs) are found through the shape's binding offsets.

Lists benefit most:

- Clearing a `For` list emits one `DISPOSE_RANGE`, plus the disposal of each row's owner.
- When a keyed list reuses no rows (every row replaced), the new rows mount as one splice and the old ones go in one `DISPOSE_RANGE`, instead of reconciling a thousand unrelated pairs.

## Event delegation

Handlers such as `on_click` don't attach native listeners per element.
The kernel installs one native listener per event type on each **render
root** (the container passed to `render`). Template nodes declare their
listener types at registration, and handlers on other nodes ride the
same buffer as a `LISTEN` command. When an event fires, the kernel walks
the ancestor chain natively and calls into Python once for the matching
route, with a small JSON payload. Handlers may take the event or no
arguments at all. See [Events](events.md).

## `render` and `Root`

[`render(vnode, container)`][wybthon.render] mounts a tree into an
[`Element`][wybthon.Element], a CSS selector, or a kernel node id,
commits the buffer, registers the container as an event root, and
returns a [`Root`][wybthon.Root]. Rendering into the same container
again patches the existing tree in place.

```python
from wybthon import h1, render

root = render(h1("Hello, world!"), "#app")
root.container  # the container Element
root.vnode  # the mounted root VNode
root.dispose()  # unmount, dispose every scope, unregister the event root
```

## Architecture

- **`vnode`**: `VNode`, `h`, `Fragment`, `hole`, and child normalization (no browser dependency).
- **`html`** and **`svg`**: tag helpers; SVG elements propagate their namespace to children.
- **`_dom_props`** (private): attribute, property, class, style, dataset, ref, and reactive-binding application, all op-based.
- **`_template`** (private): shapes, generated mount functions, lazy id materialization, and offset-based disposal.
- **`reconciler`**: mount, patch, unmount, `render`, `hydrate`, and `Root`.
- **`kernel`**: the command buffer, the JS kernel (`_kernel.js`), and the Python reference backend.
- **`events`**: the Python half of delegation and [`DomEvent`][wybthon.DomEvent].

The common names are re-exported from the top-level `wybthon` package.

## Error reporting

In dev mode, render errors are logged with the component name and a
full traceback. An [`Errored`][wybthon.Errored] boundary above the
failing subtree catches the error and shows a fallback instead.
Production builds (`wyb build`) turn dev mode off before the application
imports; call [`set_dev_mode(False)`][wybthon.set_dev_mode] yourself
when you mount outside the production bootstrap.

## Next steps

- See [Primitives](primitives.md#reactive-holes) for the hole mental model.
- Read [Lifecycle and ownership](lifecycle.md) for mount and unmount semantics.
- Browse the [`reconciler`](../api/reconciler.md) and [`kernel`](../api/kernel.md) API pages.
- Read [RFC 0002](../rfcs/0002-engine-v2.md) for the design and benchmarks behind compiled mounting.
