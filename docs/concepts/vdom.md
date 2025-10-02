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

> TODO: Document keyed diffing, normalization rules, and error boundaries interaction.
