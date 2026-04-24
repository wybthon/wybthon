### wybthon (package)

::: wybthon

#### Public API (top-level imports)

- Core rendering
  - `Element`, `Ref`
  - `VNode`, `h`, `render`, `Fragment`, `dynamic`, `is_getter`, `memo`
- Components
  - `component`, `forward_ref`, `ErrorBoundary`, `Suspense`
- Reactivity
  - `create_signal` (optional `equals=`), `create_effect`, `create_memo`, `batch`, `untrack`, `on`, `create_root`, `create_selector`
  - `on_mount`, `on_cleanup`
  - `ReactiveProps`, `get_props`, `children` (memoized children helper), `get_owner`, `run_with_owner`
  - `Resource`, `create_resource`
  - `merge_props`, `split_props`, `map_array`, `index_array`
  - Types: `Signal`, `Computed` (for type hints; create instances via `create_signal` / `create_memo`)
- Context
  - `Context`, `create_context`, `use_context`, `Provider`
- Stores
  - `create_store`, `produce`
- Flow control
  - `Show`, `For`, `Index`, `Switch`, `Match`, `Dynamic`
- Router
  - `Route`, `Router`, `Link`, `navigate`, `current_path`
- Forms
  - State and validation: `FieldState`, `form_state`, `validate`, `validate_field`, `validate_form`
  - Validators: `required`, `min_length`, `max_length`, `email`
  - Bindings and submit helpers: `bind_text`, `bind_checkbox`, `bind_select`, `on_submit`, `on_submit_validated`
  - A11y helpers: `a11y_control_attrs`, `error_message_attrs`
- Events
  - `DomEvent`
- Lazy loading
  - `lazy`, `load_component`, `preload_component`
- Development mode
  - `DEV_MODE`, `set_dev_mode`, `is_dev_mode`

!!! note "Browser vs non-browser"
    DOM/VDOM rendering (`Element`, `render`, router, etc.) requires a
    Pyodide/browser environment. In non-browser contexts the
    reactivity primitives, forms, lazy utilities, and pure-Python VDOM
    constructs (`VNode`, `h`, `Fragment`, `dynamic`, `memo`,
    `is_getter`) are still available.
