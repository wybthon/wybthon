### wybthon.template

::: wybthon.template

#### What's in this module

`template` is the runtime analogue of SolidJS's compiled templates. A
run-once component returns a tree whose *structure* is static; only
holes, event handlers, refs, and reactive prop bindings change after
mount. So the static skeleton is serialized to an HTML string once,
registered with the kernel (`REGISTER_TPL`), and every later mount of
the same shape is a single `CLONE_TPL` op. The kernel walks the clone in
pre-order and assigns a dense block of node ids, which the Python side
predicts with no read-backs.

| Name | Description |
| --- | --- |
| [`build_plan`][wybthon.template.build_plan] | Serialize an element VNode's static structure, or return `None` when the tree must use per-node ops. |
| [`MountPlan`][wybthon.template.MountPlan] | The result: `html`, the pre-order `order` list, the dynamic `bindings`, and `node_count`. |

Application code never calls these; the reconciler does.

#### How a plan is built

- Static tags, attributes, classes, styles, and datasets go into the
  HTML string directly.
- Static text is **hoisted**: it serializes as a one-space placeholder
  and is applied as a `SET_TEXT` binding after the clone. This is what
  lets a thousand list rows that differ only in their text share one
  skeleton.
- Reactive props are recorded as bindings and wrapped in per-prop render
  effects after ids are assigned; event handlers become `LISTEN` ops;
  `value`, `checked`, and `innerHTML` are applied as DOM properties.
- Dynamic children (holes, fragments, components) serialize as comment
  placeholders and are mounted at that position afterwards.
- Plans are cached per **shape**: serialization and eligibility checks
  run on the first mount of a shape, and later structurally identical
  trees are a dictionary hit.

#### When the fast path is skipped

`build_plan` returns `None`, and the reconciler falls back to per-node
ops (still batched into the same commit), when the HTML parser wouldn't
reproduce the tree faithfully: fewer than three nodes, adjacent or empty
text nodes, raw-text elements such as `<script>` and `<textarea>`, SVG
and MathML subtrees (mounted with `CREATE_ELEMENT_NS` instead), invalid
attribute names, or nestings the parser rewrites (bare text inside
`<table>`, an implied `<tbody>`, an auto-closed `<p>`). The reconciler
also skips templates when the backend can't parse HTML (a stub document
without `<template>` support). The fallback is purely a performance
difference; behavior is identical.

#### See also

- [Kernel](kernel.md): the `REGISTER_TPL` and `CLONE_TPL` ops
- [Reconciler](reconciler.md): mounts plans and wires bindings
- [Concepts: Virtual DOM](../concepts/vdom.md)
- [Guides: Performance](../guides/performance.md)
