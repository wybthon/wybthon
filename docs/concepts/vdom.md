# Virtual DOM

Wybthon keeps a small virtual DOM as a rendering implementation detail.
This page explains why it exists, how compiled templates and `h()` trees
mount through it, how reactive holes, bindings, and native regions
update, and how DOM operations reach the browser.

## Why a VDOM in a fine-grained framework?

SolidJS compiles JSX ahead of time, splitting each template into a
static skeleton and the expressions that change. Wybthon's
[compiler](compiler.md) makes the same split for t-string templates
before a module runs: each literal becomes a skeleton and a mount
function, and each dynamic expression becomes a getter, so every
instance only supplies its values.

What the VDOM adds is batching. In Pyodide every DOM call crosses the
Python-to-JavaScript bridge, which dominates rendering cost. So nothing
in the renderer touches the DOM directly:

- A component returns its markup once, usually a template instance.
- Reactive expressions inside it become **holes** and **bindings**, each updating its own node.
- When a hole re-evaluates, the **reconciler** patches only the hole's region and emits compact operations against integer node ids.
- All operations from one flush are handed to a small **JavaScript kernel** in one bridge crossing.

The reactive model is Solid's. The VDOM never diffs whole components,
only the region under a hole, and static markup never becomes VNodes at
all when it's written as a template. Removing the batch in favor of
direct DOM calls would put a bridge crossing behind every node. See
[RFC 0004](../rfcs/0004-engine-v4.md) for the design of the current
engine and [RFC 0003](../rfcs/0003-engine-v3.md) for compiled templates.

## Two ways to write markup

[Templates](templates.md) are the primary path:
`html(t"<div class={cls()}>{count()}</div>")` is compiled ahead of time
and mounts with one clone command. [`h(tag, props, *children)`][wybthon.h]
is the programmatic path, the counterpart of Solid's `h`, for markup
built by code: generated forms, recursive trees, or components that
compute their tag. The two mix freely, and they share one set of prop
appliers, so a prop means the same thing in both.

```python
from wybthon import Fragment, h, html

view = html(t'<div class="app"><h1>Hello</h1><p>Welcome</p></div>')
built = h("div", {"class": "app"}, h("h1", {}, "Hello"), h("p", {}, "Welcome"))
grouped = Fragment(h("h1", {}, "Title"), html(t"<p>Body</p>"))
```

For `h`:

- `tag` is an HTML tag, an SVG tag, or a component.
- Props are attributes, DOM properties, event handlers, `ref`, `key`, or reactive bindings.
- Children are strings, numbers, VNodes (templates included), lists (flattened), `None` (dropped), or reactive expressions (holes). A t-string isn't a child; pass it to `html()` first.

Template attributes use HTML names (`class`, `for`, `aria-label`).
`h()` props accept those and Python names, and the prop applier maps
them when it writes the attribute: `class_` becomes `class`, `html_for`
becomes `for`, and other underscores become hyphens (`aria_label`,
`data_testid`). In both styles, `True` sets a boolean attribute and
`False` or `None` removes it; `value` and `checked` are written as DOM
properties; `class` accepts a string, a list, or a `{name: bool}` dict;
and `style` accepts a string or a dict with snake- or kebab-case keys.

The compiler only rewrites templates, so an `h()` call's arguments are
evaluated when it runs. An `h()` element mounts node by node: one
create command per node, all in the same batch as everything else.

## Compiled templates

The compiler parses and validates each template literal when its module
is compiled, and writes the result into the module: the literal's
normalized parse tree as constants, and a mount function for each of
its elements. The first `html()` call of a literal rebuilds its slot
plan from that tree and installs the mount functions, with no parsing
and no code generation. A template that reaches `html()` uncompiled is
compiled there instead, once, and cached by the identity of the
t-string's `strings` tuple (holding a reference, so the identity can't
be reused). Literals are code, so that cache is bounded by the size of
the program; a template built by hand, whose strings aren't a literal's
constant, falls back to a bounded structural cache.

### What a compiled template holds

For each top-level element, a compiled template has:

- the **static skeleton**, serialized to HTML with every static attribute and all static text written in, and with a placeholder wherever a child slot sits;
- the **slot plan**: the pre-order node offset and kind of every interpolation (attribute, part of an attribute, event, ref, spread, child, or component tag);
- the **delegated event types** per offset, so cloning marks listeners natively;
- the tree it was parsed from, used for expansion (see [When templates expand](#when-templates-expand)).

Validation rejects markup the browser's HTML parser would rewrite,
such as `<tr>` directly inside `<table>` or a `<div>` inside a `<p>`,
with the template's source and the fix: a `SyntaxError` with the file
and line when the compiler finds it, or a
[`TemplateError`][wybthon.TemplateError] for a template compiled at
run time. That's what lets Python and the kernel agree on every node's
offset without reading anything back.

`html()` itself does almost nothing per call: it wraps the compiled
template with the call's values. A template with one top-level element
is one instance; several top-level nodes make a fragment of instances,
text, and values.

### One mount function per template

Each compiled element has a mount function that mounts an instance in
straight-line code, with its offsets and prop names as constants. The
compiler writes it into the module as an ordinary `def`, so a
production build turns it into bytecode with the rest of the
application. It:

1. allocates a dense block of node ids, one per node in the skeleton;
2. appends one `CLONE` command, registering the skeleton with the kernel (`REGISTER_TPL`, in the same batch) the first time it's needed;
3. walks the slot plan with the instance's values, applying each attribute, event, ref, and spread through the same appliers `h()` uses;
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

## Reactive holes and bindings

A getter, an accessor, or a zero-argument function in a child position
becomes a hole; in an attribute position (other than events and `ref`),
it becomes a binding. In a template, the compiler makes every dynamic
expression a getter, so `{count() * 2}` and `class={status()}` are a
hole and a binding. Each binding updates on its own, so unrelated
attributes on the same element update independently. Use
[`hole`][wybthon.hole] to create a hole explicitly in an `h()` tree
when you need a `key`.

```python
from wybthon import create_signal, html

count, set_count = create_signal(0)

view = html(t"<p class={'odd' if count() % 2 else 'even'}>Count: {count()} (x2={count() * 2})</p>")
```

A hole's expression may return a string, a template or other `VNode`, a
list (mounted as a fragment), `None`, or another accessor. Holes are
ownership scopes: components mounted inside one survive its
re-evaluations while the reconciler can patch them in place, and
[`on_cleanup`][wybthon.on_cleanup] inside the expression runs before
each re-run.

Bindings keep their state in slots. Each hole and attribute binding is
a small computation that holds its node, name, and last value directly,
and applies its result as a method, not through a closure and its
cells. A mounted template row therefore keeps about half as many
objects for the cyclic garbage collector to track as it did in the
previous engine; see the
[engine v4 evaluation](https://github.com/wybthon/wybthon/blob/main/benchmarks/results/engine-v4.md).

**A static probe before a computation.** A binding whose expression
makes no calls (`{props.title}`, `{row["label"]}`) first runs under a
lightweight observer. If it reads nothing reactive, creates nothing,
and returns synchronously, the value is applied and no computation is
ever allocated. The probe stops at the first reactive read, and the
binding then runs as a computation. A probe that returns an accessor
without reading anything (`{row["label"]}` returning a signal) binds
directly to that accessor.

**Inert bindings are dropped.** Any other hole or binding that finishes
its first run without reading a reactive source, and without creating
children, cleanups, or async work, can never run again. The renderer
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
- **`For` and `Repeat`** are list regions. Each row is its own owner, rows are moved rather than re-diffed, and a store list's edit records apply directly. A row's index is a plain integer until something reads `index()` in a tracking scope, which is when the signal behind it is created.

Matching a keyed list against its mounted rows skips the common prefix
and suffix by identity without calling into each row, detects swapped
ends the way Solid's `reconcileArrays` does, and only then falls back to
a key table for what's left. Swapping two rows is two native moves.

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
- Same component and key: patched in place. New props flow into the existing props instance, and the body doesn't run again.
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


html(t"<div>{editor()}</div>")
```

Prefer [`For`][wybthon.For] for lists: it caches each row's node and
scope, so rows are moved rather than re-diffed at all.

## When templates expand

Some renderers need ordinary VNodes. Server rendering, hydration, SVG
and MathML (a template containing `<svg>` or `<math>`, or one mounted
inside an SVG parent), and backends that can't parse HTML **expand** a
template into the same VNode tree `h()` would build, and mount that.
Output and hydration keys are identical whichever style you use. A
hydrated instance keeps its expanded tree, so a hole that later patches
it diffs the expanded trees; everything mounted after hydration uses
the clone path.

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
in one table keyed by node id; a node with a single handler stores it
directly, without a dictionary of its own.

## Teardown

Unmounting doesn't visit every node in Python. `DISPOSE_RANGE` removes a
contiguous range of siblings and releases every registered node inside
it, and `DISPOSE` does the same for one node's subtree; the kernel walks
the removed nodes natively. Python-side registrations (handlers,
reactive bindings, refs) are found through the template's slot plan.

Lists benefit most:

- Clearing a `For` list emits one `DISPOSE_RANGE`, plus the disposal of each row's owner.
- When a keyed list reuses no rows (every row replaced), the new rows mount as one splice and the old ones go in one `DISPOSE_RANGE`, instead of reconciling a thousand unrelated pairs.

## Event delegation

Handlers such as `onclick={save}` (or `on_click=save` in an `h()` call)
don't attach native listeners per element. The kernel installs one
native listener per event type on each **render root** (the container
passed to `render`). Template nodes declare their listener types at
registration, and handlers on other nodes ride the same buffer as a
`LISTEN` command. When an event fires, the kernel walks the ancestor
chain natively and calls into Python once for the matching route, with
a small JSON payload. Handlers may take the event or no arguments at
all. See [Events](events.md).

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

- **`compiler`**: the AST transform that defers dynamic expressions and precompiles template literals, and the import hook that runs it.
- **`templates`**: `html` and `TemplateError`: parsing, validation, the runtime fallback and its cache, mount function generation, slot-wise patching, and expansion.
- **`vnode`**: `VNode`, `h`, `Fragment`, `hole`, and child normalization (no browser dependency).
- **`_compiled`** (private): the run-time helpers compiled modules call (getters, call dispatch, format specs, precompiled entries).
- **`_dom_props`** (private): attribute, property, class, style, dataset, ref, and reactive-binding application, shared by templates and `h()`, all op-based.
- **`_html_rules`** (private): the HTML parser's content rules, used by template validation.
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
when you mount outside the production bootstrap. A malformed template
isn't a render error: the compiler rejects it when the module is
compiled, and `html()` raises [`TemplateError`][wybthon.TemplateError]
the first time an uncompiled one runs, in every mode.

## Next steps

- Read [Templates](templates.md) for the template syntax, and [The compiler](compiler.md) for what it generates.
- See [Primitives](primitives.md#reactive-holes) for the hole mental model.
- Read [Lifecycle and ownership](lifecycle.md) for mount and unmount semantics.
- Browse the [`reconciler`](../api/reconciler.md) and [`kernel`](../api/kernel.md) API pages.
- Read [RFC 0004](../rfcs/0004-engine-v4.md) for the compiler, leaner bindings, and keyed matching, and [RFC 0003](../rfcs/0003-engine-v3.md) for compiled templates and zero-cost components.
