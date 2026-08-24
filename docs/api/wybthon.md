### wybthon (package)

::: wybthon

#### Public API (top-level imports)

- Core rendering
  - `Element`, `Ref`
  - `VNode`, `h`, `render`, `Fragment`, `dynamic`, `is_getter`
- Components
  - `component`, `forward_ref`, `ErrorBoundary`, `Loading`, `LoadingList`, `Portal`
- Reactivity
  - `create_signal` (optional `equals=`; the setter also accepts an updater function), `create_effect`, `create_render_effect`, `create_memo`, `flush`, `untrack`, `create_root`, `create_selector`, `create_reaction`
  - `on_mount`, `on_cleanup`, `on_error`, `create_unique_id`, `catch_error`
  - `ReactiveProps`, `get_props`, `children` (memoized children helper), `get_owner`, `run_with_owner`
  - `merge_props`, `split_props`, `map_array`, `index_array`
  - Types: `Signal`, `Computed` (for type hints; create instances via `create_signal` / `create_memo`)
- Async
  - `NotReadyError`, `is_pending`, `latest`, `action`, `create_optimistic`
- Context
  - `Context`, `create_context`, `use_context`, `Provider`
- Stores
  - `create_store`, `create_projection`, `create_optimistic_store`, `reconcile`, `unwrap`
- Flow control
  - `Show`, `For`, `Repeat`, `Switch`, `Match`, `Dynamic`
- Router
  - `Route`, `Router`, `Link`, `navigate`, `current_path`
- Forms
  - State and validation: `FieldState`, `form_state`, `validate`, `validate_field`, `validate_form`, `rules_from_schema`
  - Validators: `required`, `min_length`, `max_length`, `email`
  - Bindings and submit helpers: `bind_text`, `bind_checkbox`, `bind_select`, `on_submit`, `on_submit_validated`
  - A11y helpers: `a11y_control_attrs`, `error_message_attrs`
- Events
  - `DomEvent`
- Lazy loading
  - `lazy`
- Development mode
  - `DEV_MODE`, `set_dev_mode`, `is_dev_mode`

!!! note "Browser vs non-browser"
    DOM/VDOM rendering (`Element`, `render`, router, `ErrorBoundary`,
    `Loading`, `LoadingList`, `Portal`, etc.) requires a Pyodide/browser
    environment. In non-browser contexts the reactivity primitives
    (including async memos, actions, and `flush`), stores, forms,
    context, flow control, and pure-Python VDOM constructs (`VNode`,
    `h`, `Fragment`, `dynamic`, `is_getter`) are still available.
