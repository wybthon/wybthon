### wybthon.vdom

::: wybthon.vdom

#### Keyed children and diffing

- `h(tag, {"key": key}, ...)` assigns a stable identity to a child.
- During reconciliation, children are matched by key first, then by type for unkeyed nodes.
- Reorders are applied with minimal DOM moves using a right-to-left pass with a moving anchor.
- Unmatched old nodes are unmounted; unmatched new nodes are mounted at the correct anchor.

#### Suspense

`Suspense` renders a `fallback` while one or more resources are loading.

- Props:
  - `resource` or `resources=[...]`
  - `fallback` – VNode/str/callable
  - `keep_previous=False` – keep children visible during subsequent reloads

#### ErrorBoundary

`ErrorBoundary` catches render errors from its subtree and renders a `fallback`.

- Props:
  - `fallback` – VNode/str/callable. When callable, it is invoked as `fallback(error, reset)`; if the callable only accepts one argument, it is invoked as `fallback(error)`.
  - `on_error` – optional callback called with the thrown error when the boundary captures it.
  - `reset_key` – any value; when this value changes, the boundary automatically resets (clears the error) on the next render.
  - `reset_keys` – list/tuple of values; when the tuple of values changes, the boundary automatically resets.

- Methods:
  - `reset()` – imperative method to clear the current error and attempt re-rendering children.

- Notes:
  - If the fallback callable throws, a simple text node "Error rendering fallback" is shown.
  - When not in an error state, the boundary renders its `children` wrapped in a `div`.
