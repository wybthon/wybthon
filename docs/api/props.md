### wybthon.props

::: wybthon.props

#### What's in this module

`props` contains the prop-level diffing helpers used by the reconciler:
attribute set/remove, class and style merging, event handler updates,
and a few utilities for normalizing prop names (`class_` → `class`,
`for_` → `for`, etc.).

You normally interact with props by passing keyword arguments to tag
helpers in [`wybthon.html`][wybthon.html] or to [`h`][wybthon.h]. The
helpers here document the semantics and edge cases.

#### Reserved prop names

| Name | Purpose |
| --- | --- |
| `children` | Explicit children list (alternative to positional args). |
| `key` | Identity hint for keyed list reconciliation. |
| `ref` | A [`Ref`][wybthon.Ref] populated when the underlying element is mounted. |
| `class_` / `className` | Both map to the DOM `class` attribute. |
| `for_` / `html_for` | Both map to the DOM `for` attribute. |
| `on_*` | Event handlers — see [`events`][wybthon.events]. |
| `style` | A dict of CSS properties or a string. |

#### See also

- [`vdom`][wybthon.vdom] — entry points for rendering and patching.
- [`events`][wybthon.events] — event delegation details.
- [Concepts → DOM Interop](../concepts/dom.md)
