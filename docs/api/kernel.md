### wybthon.kernel

::: wybthon.kernel

#### What's in this module

`kernel` is the single point of contact between the renderer and the
real DOM. The reconciler, the compiled template mounts, the prop
appliers, and the event system emit compact ops (JSON-serializable
tuples against integer node ids) into a buffer; `commit()` hands the
whole buffer to the active backend in one Python-to-JS bridge crossing.
The browser half lives in `_kernel.js`, shipped with the package.
Application code never imports this module; it matters when you're
writing low-level tests against the stub backend or debugging the wire
protocol. For component tests, use [`wybthon.testing`](testing.md).

| Name | Description |
| --- | --- |
| [`commit`][wybthon.kernel.commit] | Flush every queued op to the backend in one crossing (no-op when empty). |
| [`BrowserBackend`][wybthon.kernel.BrowserBackend] | Drives the real DOM through the JS kernel; created automatically in Pyodide. |
| [`PythonBackend`][wybthon.kernel.PythonBackend] | Reference interpreter applying the same ops to a DOM-like stub document (used by `wybthon.testing`, the unit tests, and the stubbed benchmark). |
| [`set_backend`][wybthon.kernel.set_backend] | Install a backend (tests pass a `PythonBackend`). |
| [`reset`][wybthon.kernel.reset] | Test helper: clear the op buffer, id counters, and template registry, optionally installing a backend. |

Two more module-level hooks matter to tests. `register_template(shape)`
registers the static skeleton of a compiled [`html`][wybthon.html]
template, or of an element helper's compiled shape, in the same batch
as its first clone. `html_templates` (`True`, `False`, or `None` for
"ask the backend") gates template mounting; set it to `False` to force
per-node commands.

#### Wire protocol

Each op is a JSON array whose first element is the opcode. Node ids are
allocated on the Python side, so no `JsProxy` objects flow through the
hot path; `None` anchors mean "append".

| Op | Payload | Effect |
| --- | --- | --- |
| `CREATE_ELEMENT` | `id, tag` | `document.createElement` |
| `CREATE_ELEMENT_NS` | `id, namespace, tag` | `document.createElementNS` (SVG, MathML) |
| `CREATE_TEXT` | `id, text` | `document.createTextNode` |
| `CREATE_COMMENT` | `id[, data]` | Comment marker (fragment and hole anchors); `Loading` boundaries carry a key in `data` during server rendering and hydration |
| `REGISTER_TPL` | `tpl_id, html, count, [text offsets], [[offset, event_type], ...]` | Parse a template's or shape's skeleton once via `<template>`, and record its text slots and delegated listeners |
| `CLONE` | `first_id, tpl_id, parent_id, anchor_id, *texts` | Clone the prototype, register a dense id block in pre-order, fill the text slots, mark the delegated listeners, and insert before the anchor |
| `INSERT` | `parent_id, id, anchor_id` | `insertBefore` (`None` anchor appends) |
| `REMOVE` | `id` | Detach from the parent; the node stays registered |
| `MOVE_RANGE` | `parent_id, first_id, last_id, anchor_id` | Move a contiguous mounted range |
| `DISPOSE_RANGE` | `first_id, last_id` | Remove a contiguous range of siblings and release every registered node inside it, walking the removed nodes natively |
| `DISPOSE` | `id` | Remove one node and release every registered node inside it |
| `HOLE_TEXT` | `id, text` | Reuse a hole's placeholder as a visible text node |
| `RELEASE_TPL` | `tpl_id` | Evict a native template prototype |
| `SET_TEXT` | `id, text` | `nodeValue` assignment |
| `SET_ATTR` | `id, name, value` | `setAttribute`, or `removeAttribute` when `value` is `None` |
| `SET_PROP` | `id, name, value` | DOM property assignment (`value`, `checked`, `selectedValues`, `innerHTML`) |
| `SET_STYLE` | `id, decls` | `style.setProperty` / `removeProperty` per kebab-case declaration |
| `LISTEN` / `UNLISTEN` | `id, event_type[, options]` | Delegated bookkeeping for nodes outside a template, or a direct native listener with options; unlisten omits options |
| `RELEASE` | `[ids]` | Drop registry entries and listener sets (used for a disposed root's container) |
| `ROOT` / `UNROOT` | `id` | Start or stop delegating events from this container instead of `document` |
| `HYDRATE` | `root_id` | Start claiming server-rendered nodes under `root_id` |
| `CLAIM_ELEMENT` | `id, parent_id, tag, namespace` | Adopt the parent's next element, or create one in place on a mismatch |
| `CLAIM_TEXT` | `id, parent_id, text` | Adopt the next text node, splitting text the HTML parser merged; empty text is created |
| `CLAIM_COMMENT` | `id, parent_id, data` | Adopt the next comment; a keyed end marker (`/...`) resynchronizes by searching forward |
| `CLAIM_STATIC` | `parent_id, end_marker` | Keep the server nodes before the marker as static DOM (a [`NoHydration`][wybthon.NoHydration] region) |
| `HYDRATE_END` | none | Remove server nodes nobody claimed and stop claiming |

A row of the js-framework-benchmark table costs one command, a `CLONE`
that carries the row's text and its label's first value, whether it's
written as an `html` template or with element helpers. Clearing a list
is one `DISPOSE_RANGE`. Unmounting never sends lists of every node id: the
kernel releases the removed nodes itself. See
[Virtual DOM](../concepts/vdom.md#compiled-templates) for how compiled
templates, helper shapes, generated mount functions, and lazy node ids
fit together.

[`hydrate`][wybthon.hydrate] emits the claim ops; see [Server rendering](../concepts/server-rendering.md). `stats()` reports node, template, listener, and root counts plus `hydration_mismatches`, and `take_state()` and `replay_events()` read the server state and replay input recorded before hydration.

Events travel the other way: the JS kernel installs one native listener
per event type on each render root, walks the ancestor chain natively,
and calls the Python dispatcher once for the matching bubbling route with a small
JSON payload (see [events](events.md)).

```python
from wybthon import kernel

# In a CPython test, install the stub backend over any DOM-like document
# (wybthon.testing and the test suite's conftest do this for you).
kernel.reset(kernel.PythonBackend(stub_document))
kernel.html_templates = False  # optional: force per-node commands
```

#### See also

- [Reconciler](reconciler.md): emits the ops
- [Events](events.md): the Python half of delegation
- [Testing](testing.md): the in-memory renderer built on `PythonBackend`
- [Concepts: Virtual DOM](../concepts/vdom.md)
- [Guides: Testing](../guides/testing.md)
