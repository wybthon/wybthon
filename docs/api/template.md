### wybthon.template

::: wybthon.template

#### What's in this module

`template` implements the template-based mounting fast path. When the
reconciler mounts a host-element subtree, it first asks `build_plan` to
serialize the static parts of the tree into a single HTML string. The
string is parsed once by the browser via a `<template>` element, cloned,
and then `wire_tree` walks the cloned DOM and the VNode tree in tandem to
attach element wrappers, reactive bindings, and event handlers.

This turns what would be one Python-to-JS FFI call per DOM node into a
single `innerHTML` assignment plus one short wiring pass, which is the
single biggest lever for mount performance under Pyodide.

#### How a plan is built

- Static tags, attributes, classes, styles, datasets, and text become part
  of the HTML string directly.
- Reactive props (getter callables) are recorded as bindings with a path
  to their node; they're applied during wiring and wrapped in effects.
- Event handlers (`on_*`) are recorded as bindings and attached during
  wiring through the delegated event system.
- Dynamic children (holes, components, fragments) are serialized as
  comment placeholders; the reconciler mounts them at the placeholder
  position during wiring.

#### When the fast path is skipped

`build_plan` refuses (and the reconciler falls back to node-by-node
mounting) when the subtree can't be represented faithfully as HTML, for
example: `value`/`checked` props on form controls, raw-text elements like
`<script>`, adjacent text nodes that would merge during parsing, or
environments whose DOM stub has no `<template>` support. The fallback is
purely a performance difference; behavior is identical.

#### See also

- [Concepts: Virtual DOM](../concepts/vdom.md)
- [`reconciler`][wybthon.reconciler]: mounts plans and wires bindings.
- [Guides: Performance](../guides/performance.md)
