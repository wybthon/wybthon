### wybthon.vnode

::: wybthon.vnode

#### What's in this module

`vnode` defines the framework's lightweight virtual DOM node type along
with a few pure helpers for marker nodes (`Fragment`) and reactive holes
([`dynamic`][wybthon.dynamic], [`is_getter`][wybthon.is_getter]).

A `VNode` is just a Python object with three properties:

| Field | Description |
| --- | --- |
| `tag` | A string tag (`"div"`, `"button"`), a component callable, or a special marker. |
| `props` | A dict of attributes, event handlers, and reserved props (`children`, `key`, `ref`). |
| `children` | A list of child VNodes, primitives, or callables for reactive holes. |

You usually create VNodes via [`h`][wybthon.h] or the helpers in
[`wybthon.html`][wybthon.html] rather than instantiating `VNode`
directly.

#### See also

- [`vdom`][wybthon.vdom]: render and patch primitives.
- [`reconciler`][wybthon.reconciler]: keyed list and child diffing.
- [Concepts: Virtual DOM](../concepts/vdom.md)
