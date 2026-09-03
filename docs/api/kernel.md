### wybthon.kernel

::: wybthon.kernel

#### What's in this module

`kernel` is the single point of contact between the renderer and the
real DOM. The reconciler, prop appliers, and event system emit compact
ops (JSON-serializable tuples against integer node ids) into a buffer;
`commit()` hands the whole buffer to the active backend in one
Python-to-JS bridge crossing. Application code never imports this
module; it matters when you're writing tests against the stub backend
or debugging the wire protocol.

| Name | Description |
| --- | --- |
| [`commit`][wybthon.kernel.commit] | Flush every queued op to the backend in one crossing (no-op when empty). |
| [`BrowserBackend`][wybthon.kernel.BrowserBackend] | Drives the real DOM through the embedded JS kernel; created automatically in Pyodide. |
| [`PythonBackend`][wybthon.kernel.PythonBackend] | Reference interpreter applying the same ops to a DOM-like stub document (used by the unit tests and the stubbed benchmark). |
| [`set_backend`][wybthon.kernel.set_backend] | Install a backend (tests pass a `PythonBackend`). |
| [`reset`][wybthon.kernel.reset] | Test helper: clear the op buffer, id counters, and template registry, optionally installing a backend. |

#### Wire protocol

Each op is a JSON array whose first element is the opcode. Node ids are
allocated on the Python side, so no `JsProxy` objects flow through the
hot path; `None` anchors mean "append".

| Op | Payload | Effect |
| --- | --- | --- |
| `CREATE_ELEMENT` | `id, tag` | `document.createElement` |
| `CREATE_ELEMENT_NS` | `id, namespace, tag` | `document.createElementNS` (SVG, MathML) |
| `CREATE_TEXT` | `id, text` | `document.createTextNode` |
| `CREATE_COMMENT` | `id` | Empty comment marker (fragment and hole anchors) |
| `REGISTER_TPL` | `tpl_id, html` | Parse a skeleton once via `<template>` |
| `CLONE_TPL` | `first_id, count, tpl_id` | Clone the proto; assign a dense id block in pre-order |
| `INSERT` | `parent_id, id, anchor_id` | `insertBefore` (`None` anchor appends) |
| `REMOVE` | `id` | Detach from the parent |
| `SET_TEXT` | `id, text` | `nodeValue` assignment |
| `SET_ATTR` | `id, name, value` | `setAttribute`, or `removeAttribute` when `value` is `None` |
| `SET_PROP` | `id, name, value` | DOM property assignment (`value`, `checked`, `innerHTML`) |
| `SET_STYLE` | `id, decls` | `style.setProperty` / `removeProperty` per kebab-case declaration |
| `LISTEN` / `UNLISTEN` | `id, event_type` | Delegated handler bookkeeping plus per-root listener refcounts |
| `RELEASE` | `[ids]` | Drop registry entries and listener sets for a retired subtree |
| `ROOT` / `UNROOT` | `id` | Start or stop delegating events from this container instead of `document` |

Events travel the other way: the JS kernel installs one native listener
per event type on each render root, walks the ancestor chain natively,
and calls the Python dispatcher once per matched handler with a small
JSON payload (see [events](events.md)).

```python
from wybthon import kernel

# In a CPython test, install the stub backend over any DOM-like document
# (the test suite's conftest does this for you).
kernel.reset(kernel.PythonBackend(stub_document))
```

#### See also

- [Reconciler](reconciler.md): emits the ops
- [Template](template.md): `REGISTER_TPL` and `CLONE_TPL` in practice
- [Events](events.md): the Python half of delegation
- [Concepts: Virtual DOM](../concepts/vdom.md)
- [Guides: Testing](../guides/testing.md)
