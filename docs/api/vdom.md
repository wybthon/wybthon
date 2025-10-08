### wybthon.vdom

::: wybthon.vdom

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
