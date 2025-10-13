### wybthon.reactivity

::: wybthon.reactivity

#### Public API

- `signal(value) -> Signal[T]`
- `computed(fn) -> _Computed[T]` with `.get()` and `.dispose()`
- `effect(fn) -> Computation` (returns a handle; call `.dispose()` to stop)
- `on_effect_cleanup(comp, fn)`
- `batch() -> context manager`
- `Resource(fetcher)` and `use_resource(fetcher) -> Resource`

Type hints are provided for all public functions and classes. Prefer retrieving values via `.get()` on signals and computed values to subscribe computations.
