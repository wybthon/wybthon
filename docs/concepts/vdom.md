### Virtual DOM

The VDOM is represented by `VNode` and created via `h(tag, props, *children)`.

- `tag`: string (DOM node) or callable (component)
- `props`: attributes, event handlers, and special props like `key`
- `children`: strings or `VNode`s

```python
from wybthon import h

view = h("div", {"class": "app"},
          h("h1", {}, "Hello"),
          h("p", {}, "Welcome"))
```

Rendering is done with `vdom.render(view, container)`.

Keyed diffing

- Provide `key` on children of dynamic lists: `h("li", {"key": item.id}, ...)`.
- Keys allow Wybthon to match, reorder, insert, and remove children with minimal DOM changes while preserving element identity and state.
- The reconciler first matches children by key, then falls back to type-matching for unkeyed nodes.
