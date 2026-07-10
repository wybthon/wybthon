### wybthon.kernel

::: wybthon.kernel

#### What's in this module

`kernel` is the single point of contact between Wybthon's renderer and
the real DOM. The reconciler, prop appliers, and event system never
call DOM APIs; they emit compact operations (JSON-serializable tuples
against integer node ids) into a buffer that `commit()` flushes to the
active backend in one Python-to-JS bridge crossing.

Two backends implement the protocol:

- `BrowserBackend` drives the real DOM through a small JavaScript
  kernel evaluated once in the page. The kernel owns the id-to-node
  registry, the registered template protos (parsed once, cloned per
  mount), and native event delegation.
- `PythonBackend` is a reference interpreter that applies the same ops
  to any DOM-like stub document. The unit tests and the stubbed
  benchmark run the full wire protocol through it, so protocol bugs
  surface without a browser.

#### The op protocol

| Op | Payload | Effect |
| --- | --- | --- |
| `CREATE_ELEMENT` | `id, tag` | `document.createElement` |
| `CREATE_TEXT` | `id, text` | `document.createTextNode` |
| `CREATE_COMMENT` | `id` | `document.createComment` |
| `REGISTER_TPL` | `tpl_id, html` | Parse a skeleton once via `<template>` |
| `CLONE_TPL` | `first_id, count, tpl_id` | Clone the proto; assign a dense id block in pre-order |
| `INSERT` | `parent_id, id, anchor_id` | `insertBefore` (`None` anchor appends) |
| `REMOVE` | `id` | Detach from parent |
| `SET_TEXT` | `id, text` | `nodeValue` assignment |
| `SET_ATTR` | `id, name, value` | `setAttribute` / `removeAttribute` (`None` removes) |
| `SET_PROP` | `id, name, value` | DOM property assignment (`value`, `checked`) |
| `SET_STYLE` | `id, decls` | `style.setProperty` / `removeProperty` per declaration |
| `LISTEN` / `UNLISTEN` | `id, type` | Delegated handler bookkeeping plus root-listener refcounts |
| `RELEASE` | `[ids]` | Drop registry entries and listener sets for a retired subtree |

Application code never imports this module directly; it's plumbing for
the reconciler, `wybthon.props`, and `wybthon.events`.

#### See also

- [Concepts: Virtual DOM](../concepts/vdom.md)
- [`template`][wybthon.template]: the skeleton registration fast path.
- [`reconciler`][wybthon.reconciler]: emits the ops.
