### wybthon.reactivity

::: wybthon.reactivity

#### Public API

##### Signals-first API (recommended)

- `create_signal(value) -> (getter, setter)`
- `create_effect(fn) -> Computation` — supports previous value: `create_effect(lambda prev: ...)`
- `create_memo(fn) -> getter`
- `on_mount(fn)` — run after first render
- `on_cleanup(fn)` — run on unmount or before effect re-execution
- `batch() -> context manager` or `batch(fn) -> result` — callback form flushes synchronously

##### Resources

- `create_resource(fetcher) -> Resource`
- `create_resource(source, fetcher) -> Resource` — refetches when source changes

##### Reactive utilities

- `untrack(fn)` — run without tracking signal reads
- `on(deps, fn, defer=False)` — effect with explicit deps
- `create_root(fn)` — independent reactive scope
- `merge_props(*sources)` — merge prop dicts
- `split_props(props, *key_groups)` — split props by key name

Type hints are provided for all public functions and classes.
