### wybthon.reactivity

::: wybthon.reactivity

#### Public API

##### Core reactive primitives

- `signal(value) -> Signal[T]`
- `computed(fn) -> _Computed[T]` with `.get()` and `.dispose()`
- `effect(fn) -> Computation` (returns a handle; call `.dispose()` to stop)
- `on_effect_cleanup(comp, fn)`
- `batch() -> context manager`

##### Signals-first API (recommended for `@component`)

- `create_signal(value) -> (getter, setter)`
- `create_effect(fn) -> Computation`
- `create_memo(fn) -> getter`
- `on_mount(fn)` — run after first render
- `on_cleanup(fn)` — run on unmount
- `get_props() -> getter` — reactive props accessor

##### Resources

- `create_resource(fetcher) -> Resource`
- `create_resource(source, fetcher) -> Resource` — refetches when source changes

##### Reactive utilities

- `untrack(fn)` — run without tracking signal reads
- `on(deps, fn, defer=False)` — effect with explicit deps
- `create_root(fn)` — independent reactive scope
- `merge_props(*sources)` — merge prop dicts
- `split_props(props, *key_groups)` — split props by key name

Type hints are provided for all public functions and classes. Prefer retrieving values via `.get()` on signals and computed values to subscribe computations.
