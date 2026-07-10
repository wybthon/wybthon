### wybthon.template

::: wybthon.template

#### What's in this module

`template` implements the template-based mounting fast path. When the
reconciler mounts a host-element subtree, it first asks `build_plan` to
serialize the static skeleton of the tree into a single HTML string
(with text content hoisted out). The skeleton is registered with the
rendering kernel once, parsed by the browser via a `<template>`
element, and every mount is a single *clone* op. The kernel walks the
clone in a deterministic pre-order, assigning a dense block of node
ids, so Python can address every node with no read-backs; text,
bindings, and dynamic children are then wired by id in the same
batched commit.

Hoisting text is what makes templates shared: a thousand list rows
that differ only in their ids and labels serialize to the *same*
skeleton, so the browser parses it once and clones it a thousand
times, exactly like SolidJS's compiled templates.

#### How a plan is built

- Static tags, attributes, classes, styles, and datasets become part
  of the HTML string directly.
- Static text serializes as a one-space placeholder; the real value is
  recorded as a `SET_TEXT` binding applied after the clone.
- Reactive props (getter callables) are recorded as bindings; they're
  wrapped in per-prop effects after id assignment.
- Event handlers (`on_*`) are recorded as bindings and registered
  through the kernel's delegated event system (`LISTEN` ops).
- `value`/`checked` are recorded as DOM-property bindings and assigned
  post-clone, matching the per-node mount path exactly.
- Dynamic children (holes, components, fragments) are serialized as
  comment placeholders; the reconciler mounts them at the placeholder
  position after id assignment.

#### When the fast path is skipped

`build_plan` refuses (and the reconciler falls back to per-node ops,
still batched in the same commit) when the subtree can't be
represented faithfully as HTML, for example: raw-text elements like
`<script>`, adjacent text nodes that would merge during parsing,
element nestings the parser rewrites (bare text in `<table>`,
auto-closed `<p>`, and similar), or environments whose DOM stub has no
`<template>` support. The fallback is purely a performance difference;
behavior is identical.

#### See also

- [Concepts: Virtual DOM](../concepts/vdom.md)
- [`reconciler`][wybthon.reconciler]: mounts plans and wires bindings.
- [Guides: Performance](../guides/performance.md)
