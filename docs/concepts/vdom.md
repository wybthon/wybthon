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

Rendering is done with `render(view, container)`.

#### Architecture

The VDOM implementation is split into focused modules:

- **`vnode`** — the `VNode` data structure, `h()`, `Fragment`, and `memo()` (browser-agnostic). `Fragment` does not insert a wrapper element; reconciliation uses comment-node boundaries so the DOM tree stays free of extra spans and CSS selectors stay predictable.
- **`reconciler`** — the mount/patch/unmount diffing engine
- **`props`** — DOM property application and diffing (styles, events, datasets)
- **`error_boundary`** — the `ErrorBoundary` component
- **`suspense`** — the `Suspense` component
- **`portal`** — the `create_portal()` function

All names are re-exported from `wybthon.vdom` for convenience, and the most
common ones are available at the top-level `wybthon` package.

#### Keyed diffing

- Provide `key` on children of dynamic lists: `h("li", {"key": item.id}, ...)`.
- Keys allow Wybthon to match, reorder, insert, and remove children with minimal DOM changes while preserving element identity and state.
- The reconciler first matches children by key, then falls back to type-matching for unkeyed nodes.

#### Error reporting

In development mode (`DEV_MODE = True`, the default), rendering errors include
the component name and a full traceback printed to stderr. This makes it easy
to locate problems in component trees. Set `set_dev_mode(False)` for production
to suppress verbose tracebacks.
