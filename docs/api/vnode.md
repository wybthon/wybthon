### wybthon.vnode

::: wybthon.vnode

#### What's in this module

`vnode` defines the framework's lightweight virtual DOM node type along
with a few pure helpers for marker nodes (`Fragment`) and reactive holes
([`dynamic`][wybthon.dynamic], [`expr`][wybthon.expr],
[`is_getter`][wybthon.is_getter]).

A `VNode` is an unmounted declaration with four properties. It doesn't
store DOM IDs, component owners, or effects, so one declaration can be
mounted in multiple locations safely.

| Field | Description |
| --- | --- |
| `tag` | A string tag (`"div"`, `"button"`), a component callable, or a special marker. |
| `props` | A dict of attributes, event handlers, and reserved props (`children`, `key`, `ref`). |
| `children` | A list of child VNodes, primitives, or explicit reactive accessors. |
| `key` | An optional stable identity for reconciliation. |

You usually create VNodes via [`h`][wybthon.h] or the helpers in
[`wybthon.html`][wybthon.html] rather than instantiating `VNode`
directly.

#### See also

- [`reconciler`][wybthon.reconciler]: render, patch, and keyed child diffing.
- [`runtime`][wybthon.runtime]: mount handles and isolated runtimes.
- [Concepts: Virtual DOM](../concepts/vdom.md)
