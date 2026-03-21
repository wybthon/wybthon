### wybthon.store

::: wybthon.store

#### Public API

##### Store creation

- `create_store(initial) -> (store, set_store)` — create a reactive store from a dict or list

##### Store setter

The `set_store` setter supports several calling conventions:

- `set_store("key", value)` — set a top-level key
- `set_store("key", fn)` — functional update (fn receives current value)
- `set_store("a", "b", value)` — nested path
- `set_store("a", 0, "done", True)` — path with list index
- `set_store(produce(fn))` — batch mutations via produce
- `set_store({"a": 1, "b": 2})` — update multiple top-level keys
- `set_store(fn)` — functional update on the entire store (fn receives raw data)

##### Produce

- `produce(fn)` — create a producer for batch-mutating store state; pass to `set_store`

Type hints are provided for all public functions and classes.
