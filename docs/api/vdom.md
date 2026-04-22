### wybthon.vdom

::: wybthon.vdom

The VDOM system is implemented as a set of focused sub-modules. The
`wybthon.vdom` module re-exports all public names for convenience:

| Module                      | Responsibility                                       |
|-----------------------------|------------------------------------------------------|
| `wybthon.vnode`             | `VNode`, `h()`, `Fragment`, `memo()`                 |
| `wybthon.reconciler`        | `render()`, `mount()`, `unmount()`, `patch()`        |
| `wybthon.props`             | DOM prop application, style/event/dataset diffing    |
| `wybthon.error_boundary`    | `ErrorBoundary` component                            |
| `wybthon.suspense`          | `Suspense` component                                 |
| `wybthon.portal`            | `create_portal()`                                    |

You can import from either `wybthon.vdom` or the specific sub-module:

```python
from wybthon.vdom import h, render          # re-export hub
from wybthon.vnode import h                 # direct import
from wybthon.reconciler import render       # direct import
```

#### Public API

- `VNode`
- `h(tag, props=None, *children) -> VNode`
- `Fragment(*children)` — groups children **without** a wrapper element; the reconciler uses invisible comment markers and mounts children in the parent (no `display:contents` span).
- `render(vnode, container) -> Element`
- `dynamic(getter, *, key=None) -> VNode` — wrap a zero-arg callable as a
  *reactive hole* (see [Primitives → Reactive Holes](../concepts/primitives.md#reactive-holes)).  Callable children passed to `h()` are auto-wrapped via this helper.
- `is_getter(value) -> bool` — predicate the reconciler uses to decide whether
  a callable child or prop value is a reactive hole.  Useful when authoring
  components or helpers that need to detect getters explicitly.
- `ErrorBoundary` component
- `Suspense` component
- `memo(component, are_props_equal=None)` — memoize a function component
- `create_portal(children, container)` — render children into a different DOM container

#### Keyed children and diffing

- `h(tag, {"key": key}, ...)` assigns a stable identity to a child.
- During reconciliation, children are matched by key first, then by type for unkeyed nodes.
- Reorders are applied with minimal DOM moves using a right-to-left pass with a moving anchor.
- Unmatched old nodes are unmounted; unmatched new nodes are mounted at the correct anchor.

#### Text nodes (fast-path)

- When both the old and new nodes are text, the same DOM text node is reused and only `nodeValue` is updated.
- Lists of plain text children are reconciled efficiently; typically the framework updates text in-place and minimizes DOM moves.
- Example:

```python
from wybthon import h, render
from wybthon.dom import Element

root = Element(node=document.createElement("div"))
render(h("div", {}, "hello"), root)
render(h("div", {}, "world"), root)  # updates the same text node
```

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
  - When not in an error state, the boundary renders its `children` wrapped in a `Fragment`.

#### Prop semantics (style, dataset, value, checked)

- `style`: pass a dict of CSS properties using camelCase keys. Keys are converted to kebab-case and applied via `style.setProperty`. On updates, keys that are absent in the new dict are removed with `style.removeProperty`. Passing `None` or a non-dict clears previously set style keys.

  ```python
  h("div", {"style": {"backgroundColor": "red", "fontSize": 14}})
  # → sets background-color: red; font-size: 14
  ```

- `dataset`: pass a dict; entries map to `data-*` attributes. On updates, keys not present are removed. Passing `None` or a non-dict clears previously set `data-*` attributes.

  ```python
  h("div", {"dataset": {"id": "x", "role": "button"}})
  # → sets data-id="x" data-role="button"
  ```

- `value`: for form controls, the DOM `value` property is set (falling back to the `value` attribute if needed). `None` becomes "". Removing the `value` prop resets it to "".

- `checked`: for checkboxes/radios, the DOM `checked` property is set when available (falling back to the `checked` attribute). Removing the `checked` prop clears it to `False`.

#### memo

`memo(component, are_props_equal=None)` wraps a function component to skip re-renders when props are unchanged.

- By default, uses shallow identity comparison (`is`) on each prop value.
- Pass a custom `are_props_equal(old_props, new_props) -> bool` for deeper comparison.

```python
from wybthon import memo

def ExpensiveList(props):
    # ... render a large list ...
    pass

MemoList = memo(ExpensiveList)
```

#### create_portal

`create_portal(children, container)` renders children into a different DOM container.

- *children*: a single VNode or a list of VNodes.
- *container*: an `Element` or CSS selector string.

```python
from wybthon import create_portal, h

portal = create_portal(h("div", {}, "Modal content"), "#modal-root")
```

#### Development mode

Wybthon includes a development mode (`DEV_MODE = True` by default) that provides
clear error messages to stderr when something goes wrong during rendering, event
handling, or lifecycle hooks. Errors include component names and tracebacks.

```python
from wybthon import set_dev_mode

set_dev_mode(False)  # disable for production
```
