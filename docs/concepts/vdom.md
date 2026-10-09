# Virtual DOM

Wybthon keeps a small virtual DOM as a rendering implementation detail.
This page explains why it exists, how compiled templates and element
helpers mount through it, how reactive holes, bindings, and native
regions update, and how DOM operations reach the browser.

## Why a VDOM in a fine-grained framework?

SolidJS compiles JSX ahead of time, splitting each template into a
static skeleton and the expressions that change. Wybthon gets that
split from the language: a t-string literal's static strings are the
same object every time it runs, so each literal is compiled once, and
every instance only supplies its interpolated values.

What the VDOM adds is batching. In Pyodide every DOM call crosses the
Python-to-JavaScript bridge, which dominates rendering cost. So nothing
in the renderer touches the DOM directly:

- A component returns its markup once, usually a template instance.
- Reactive expressions inside it become **holes** and **bindings**, each with its own render effect.
- When a hole re-evaluates, the **reconciler** patches only the hole's region and emits compact operations against integer node ids.
- All operations from one flush are handed to a small **JavaScript kernel** in one bridge crossing.

The reactive model is Solid's. The VDOM never diffs whole components,
only the region under a hole, and static markup never becomes VNodes at
all when it's written as a template. Removing the batch in favor of
direct DOM calls would put a bridge crossing behind every node. See
[RFC 0003](../rfcs/0003-engine-v3.md) for the design and benchmarks of
the current engine.

## Two ways to write markup

[Templates](templates.md) are the primary path:
`html(t"<div class={cls}>{count}</div>")` compiles once per literal and
mounts with one clone command. The [element helpers](../api/elements.md)
(`div(...)`, `p(...)`) and [`h(tag, props, *children)`][wybthon.h] are
the programmatic path, the counterpart of Solid's `h`, for markup built
by code: generated forms, recursive trees, or components that compute
their tag. The two mix freely, and they share one set of prop appliers,
so a prop means the same thing in both.

```python
from wybthon import Fragment, div, h, h1, html, p

view = html(t'<div class="app"><h1>Hello</h1><p>Welcome</p></div>')
same = div(h1("Hello"), p("Welcome"), class_="app")
built = h("div", {"class": "app"}, h("h1", {}, "Hello"), h("p", {}, "Welcome"))
items = div(class_="app")[h1("Hello"), p("Welcome")]
grouped = Fragment(h1("Title"), p("Body"))
```

For the helpers and `h`:

- `tag` is an HTML tag, an SVG tag, or a component.
- Props are attributes, DOM properties, event handlers, `ref`, `key`, or reactive bindings.
- Children are strings, numbers, VNodes (templates included), lists (flattened), `None` (dropped), template strings, or reactive expressions (holes).

Template attributes use HTML names (`class`, `for`, `aria-label`).
Helper props are Pythonic, and the prop applier maps them when it
writes the attribute: `class_` becomes `class`, `html_for` becomes
`for`, and other underscores become hyphens (`aria_label`,
`data_testid`). In both styles, `True` sets a boolean attribute and
`False` or `None` removes it; `value` and `checked` are written as DOM
properties; `class` accepts a string, a list, or a `{name: bool}` dict;
and `style` accepts a string or a dict with snake- or kebab-case keys.
Use [`element("my-tag")`][wybthon.element] for custom elements built in
code.

## Compiled templates

A template is compiled the first time its literal runs. The private
`wybthon.templates` module does the work, and caches the result by the
identity of the t-string's `strings` tuple (holding a reference, so the
identity can't be reused). Literals are code, so the cache is bounded
by the size of the program. A template built by hand, whose strings
aren't a literal's constant, falls back to a bounded structural cache.

### What a compiled template holds

Compilation parses the markup, validates it, and produces, for each
top-level element:

- the **static skeleton**, serialized to HTML with every static attribute and all static text written in, and with a placeholder wherever a child slot sits;
- the **slot plan**: the pre-order node offset and kind of every interpolation (attribute, part of an attribute, event, ref, spread, child, or component tag);
- the **delegated event types** per offset, so cloning marks listeners natively;
- the tree it was parsed from, used for expansion (see [When templates expand](#when-templates-expand)).

Validation rejects markup the browser's HTML parser would rewrite,
such as `<tr>` directly inside `<table>` or a `<div>` inside a `<p>`,
by raising [`TemplateError`][wybthon.TemplateError] with the template's
source and the fix. That's what lets Python and the kernel agree on
every node's offset without reading anything back.

`html()` itself does almost nothing per call: it looks up the compiled
template by identity and wraps it with the call's values. A template
with one top-level element is one instance; several top-level nodes
make a fragment of instances, text, and values.

### One generated mount function per template

Each compiled template gets a generated Python function that mounts
an instance in straight-line code, with its offsets and prop names as
constants. It:

1. allocates a dense block of node ids, one per node in the skeleton;
2. appends one `CLONE` command, registering the skeleton with the kernel (`REGISTER_TPL`, in the same batch) the first time it's needed;
3. walks the slot plan with the instance's values, applying each attribute, event, ref, and spread through the same appliers the helpers use;
4. fills each child slot and mounts each component tag at its placeholder;
5. records each slot's state on the instance, for patching and teardown.

There are no structural guards and no VNodes for the static parts: the
literal guarantees its own structure.

### The clone command and placeholders

`CLONE` clones the registered `<template>`, registers its nodes in
pre-order, fills its text slots, marks its delegated listeners, and
inserts the clone before an anchor, all in one command:
`[CLONE, first_id, tpl_id, parent_id, anchor_id, *texts]`.

A child slot keeps its placeholder as a permanent anchor:

- When the slot's neighbors aren't text or another child slot, the placeholder is a one-space text node. A text value (a string or number) is written straight into the clone command, so a row's label costs no extra command. A reactive hole whose first result is text fills that slot of the command too, and later text results are a single `nodeValue` write (`HOLE_TEXT`).
- Otherwise the placeholder is an empty comment.
- A node, list, or component is mounted in front of the placeholder, and the placeholder stays. Nothing is created and then thrown away.

A component tag (`<{Card}>`) always gets a comment placeholder, and the
component mounts in front of it.

### Patching slot by slot

When a reactive hole re-runs and returns a template from the same
literal as before, the reconciler doesn't diff a tree. It walks the
slot plan and compares each value with the previous one by identity, as
lit-html does:

- An unchanged slot costs one comparison.
- A changed text value is one `SET_TEXT` write.
- A changed attribute, event handler, ref, or spread is re-applied.
- A child slot's new value is patched into its region, and a component tag's component is patched with its new props, so its state survives.

A template from a different literal replaces the instance.

## Element helper shapes

Element helpers build ordinary VNodes, and repeated helper subtrees
mount through compiled **shapes**, the runtime shape compiler from
[RFC 0002](../rfcs/0002-engine-v2.md), in the private `wybthon._shapes`
module. The first mount of a helper subtree walks it once and records
its shape: the skeleton HTML (validated like a template's), the
pre-order node count, each text slot's offset, each binding's offset
and kind, and each dynamic child's offset. Static text is hoisted out
of the HTML, so subtrees that differ only in text (list rows) share one
skeleton. Shapes are cached by structure.

A shape gets a generated mount function too. Unlike a template's, it
first guards the instance's structure, without allocating, because a
helper tree carries no guarantee of its own shape; if a guard fails, it
falls back to the generic path. Then it allocates ids, appends one
fused `CLONE`, wires bindings by offset, and mounts dynamic children.
Every helper instance still builds its whole VNode tree first, which is
the cost templates avoid.

A component, fragment, or list child of a helper subtree mounts in
front of the element that follows it, or appends when it's last. Only
when text or another dynamic child follows it does it get a comment
placeholder, which is disposed once the child has mounted in front of
it.

Helper subtrees also keep their VNodes, but only the root and the
dynamic children get node ids at mount. Static descendants get ids the
first time the reconciler needs them, when a hole patches the subtree.
List rows and component output are never patched that way, so they
skip the work entirely.

Helper subtrees the HTML parser would rewrite, single-node subtrees,
adjacent or empty text, and raw-text elements such as `<script>` and
`<textarea>` fall back to per-node commands, still batched in the same
commit. Unlike templates, helpers don't raise for markup the parser
would rewrite: they mount it node by node.

## Reactive holes and bindings

A zero-arg callable or accessor in a child position becomes a hole; in
an attribute position (other than events and `ref`), it becomes a
binding. Each is a render effect, so unrelated attributes on the same
element update independently. Use [`hole`][wybthon.hole] to create a
hole explicitly when you need a `key`.

```python
from wybthon import create_signal, hole, html

count, set_count = create_signal(0)


def doubled():
    return f" (x2={count() * 2})"


def bang():
    return "!" * count()


def parity():
    return "odd" if count() % 2 else "even"


view = html(t"<p class={parity}>Count: {count}{doubled}{hole(bang, key='bang')}</p>")
```

A hole's expression may return a string, a template or other `VNode`, a
list (mounted as a fragment), `None`, or another accessor. Holes are
ownership scopes: components mounted inside one survive its
re-evaluations while the reconciler can patch them in place, and
[`on_cleanup`][wybthon.on_cleanup] inside the expression runs before
each re-run.

**Inert bindings are dropped.** When a hole or binding finishes its
first run without reading a reactive source, and without creating
children, cleanups, or async work, it can never run again. The renderer
disposes it immediately and keeps only the DOM it produced. Together
with constant props that subscribe to nothing (see
[What props cost](components.md#what-props-cost)), a component whose
props never change costs about what its markup costs.

## Native regions

[`Show`][wybthon.Show], [`Switch`][wybthon.Switch],
[`For`][wybthon.For], and [`Repeat`][wybthon.Repeat] aren't components.
They return region nodes that the reconciler mounts directly, with no
component context, props object, or wrapper memo:

- **`Show` and `Switch`** are one branch computation. It selects a branch from the condition and re-mounts the content only when the selected branch changes, between two comment markers.
- **`For` and `Repeat`** are list regions. Each row has its own owner, rows are moved rather than re-diffed, and a store list's edit records apply directly.

When a reactive hole re-renders a region of the same kind, the new
condition or source is pushed into the mounted region instead of
remounting it. That's the only part that was ever reactive, so rows and
branch state survive.

## The reconciler

When a hole re-evaluates, [`patch`](../api/reconciler.md) compares the
old result with the new one:

- Same VNode instance (for example a cached `For` row): skipped.
- Template instances from the same literal: patched slot by slot.
- Regions of the same kind: the new condition or source is pushed in.
- Same component and key: patched in place. New props flow into the existing accessors, and the body doesn't run again.
- Same element tag and key: props are diffed, text is updated, and children are reconciled.
- Anything else: the old subtree is unmounted and the new one mounted at the same position.

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
def editor():
    return Editor(user_id=current_id(), key=current_id())


html(t"<div>{editor}</div>")
```

Prefer [`For`][wybthon.For] for lists: it caches each row's node and
scope, so rows are moved rather than re-diffed at all.

## When templates expand

Some renderers need ordinary VNodes. Server rendering, hydration, SVG
and MathML (a template containing `<svg>` or `<math>`, or one mounted
inside an SVG parent), and backends that can't parse HTML **expand** a
template into the same VNode tree the element helpers would build, and
mount that. Output and hydration keys are identical whichever style you
use. A hydrated instance keeps its expanded tree, so a hole that later
patches it diffs the expanded trees; everything mounted after hydration
uses the clone path.

## The batched rendering kernel

The reconciler, templates, and prop appliers *emit* operations such as
clone, insert, set-text, and set-attr against integer node ids into a
command buffer. At each commit point (the end of `render`, the DOM
phase of every flush) the buffer is serialized once and handed to the
JS kernel, which applies every operation natively and keeps an
`id -> Node` registry. A mount of a thousand-row table is one bridge
crossing instead of tens of thousands. The [`kernel`](../api/kernel.md)
page documents the wire protocol.

The same protocol drives a pure-Python backend
(`kernel.PythonBackend`) that applies the ops to an in-memory stub
document. Unit tests, [`wybthon.testing`](../api/testing.md), and the
stubbed benchmark run against it, so all of them exercise exactly what
the browser sees. See the [Testing guide](../guides/testing.md).

### Template-declared listeners

Template registration lists the delegated event types at each offset.
Cloning an instance marks those listeners natively, so mounting a row
with two handlers sends no `LISTEN` commands. Python stores the handlers
in one table keyed by node id.

## Teardown

Unmounting doesn't visit every node in Python. `DISPOSE_RANGE` removes a
contiguous range of siblings and releases every registered node inside
it, and `DISPOSE` does the same for one node's subtree; the kernel walks
the removed nodes natively. Python-side registrations (handlers,
reactive bindings, refs) are found through the template's slot plan or
the shape's binding offsets.

Lists benefit most:

- Clearing a `For` list emits one `DISPOSE_RANGE`, plus the disposal of each row's owner.
- When a keyed list reuses no rows (every row replaced), the new rows mount as one splice and the old ones go in one `DISPOSE_RANGE`, instead of reconciling a thousand unrelated pairs.

## Event delegation

Handlers such as `onclick={save}` (or `on_click=save` on a helper)
don't attach native listeners per element. The kernel installs one
native listener per event type on each **render root** (the container
passed to `render`). Template and shape nodes declare their listener
types at registration, and handlers on other nodes ride the same buffer
as a `LISTEN` command. When an event fires, the kernel walks the
ancestor chain natively and calls into Python once for the matching
route, with a small JSON payload. Handlers may take the event or no
arguments at all. See [Events](events.md).

## `render` and `Root`

[`render(vnode, container)`][wybthon.render] mounts a tree into an
[`Element`][wybthon.Element], a CSS selector, or a kernel node id,
commits the buffer, registers the container as an event root, and
returns a [`Root`][wybthon.Root]. Rendering into the same container
again patches the existing tree in place.

```python
from wybthon import html, render

root = render(html(t"<h1>Hello, world!</h1>"), "#app")
root.container  # the container Element
root.vnode  # the mounted root VNode
root.dispose()  # unmount, dispose every scope, unregister the event root
```

## Architecture

- **`templates`**: `html` and `TemplateError`: parsing, validation, the per-literal cache, generated mount functions, slot-wise patching, and expansion.
- **`vnode`**: `VNode`, `h`, `Fragment`, `hole`, and child normalization (no browser dependency).
- **`elements`** and **`svg`**: the element helpers; SVG elements propagate their namespace to children.
- **`_dom_props`** (private): attribute, property, class, style, dataset, ref, and reactive-binding application, shared by templates and helpers, all op-based.
- **`_shapes`** (private): helper shapes, their generated mount functions, lazy id materialization, and offset-based disposal.
- **`_html_rules`** (private): the HTML parser's content rules, shared by template validation and helper shapes.
- **`_regions`** (private): the native `Show`, `Switch`, `For`, and `Repeat` regions.
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
when you mount outside the production bootstrap. A
[`TemplateError`][wybthon.TemplateError] isn't a render error: it's
raised by `html()` the first time a malformed template runs, in every
mode.

## Next steps

- Read [Templates](templates.md) for the template syntax.
- See [Primitives](primitives.md#reactive-holes) for the hole mental model.
- Read [Lifecycle and ownership](lifecycle.md) for mount and unmount semantics.
- Browse the [`reconciler`](../api/reconciler.md) and [`kernel`](../api/kernel.md) API pages.
- Read [RFC 0003](../rfcs/0003-engine-v3.md) for compiled templates and zero-cost components, and [RFC 0002](../rfcs/0002-engine-v2.md) for helper shapes.
