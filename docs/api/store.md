### wybthon.store

::: wybthon.store

#### Public API

##### Store creation

- `create_store(initial) -> (store, set_store)`. Create a reactive store from a dict or list.
- `create_mutable(initial) -> proxy`. Create a directly-writable store proxy (Solid's `createMutable`); top-level attribute and item assignment notify the touched key. Nested containers remain read-only proxies.

##### Store setter

The `set_store` setter supports several calling conventions:

- `set_store("key", value)`. Set a top-level key.
- `set_store("key", fn)`. Functional update (fn receives current value).
- `set_store("a", "b", value)`. Nested path.
- `set_store("a", 0, "done", True)`. Path with list index.
- `set_store(produce(fn))`. Batch mutations via produce.
- `set_store({"a": 1, "b": 2})`. Update multiple top-level keys.
- `set_store(fn)`. Functional update on the entire store (fn receives raw data).

##### Produce

- `produce(fn)`. Create a producer for batch-mutating store state; pass to `set_store`.

##### Reconcile and unwrap

- `reconcile(data, key="id")`. Create a reconcile marker for `set_store`: the new data is **diffed** into the existing state so only changed paths notify. List items are matched by `key`, preserving proxy identity across updates (important for `For`).
- `unwrap(value)`. Return the raw data underneath a store proxy without tracking. Plain values pass through unchanged.

```python
set_store("todos", reconcile(fetched_todos))
raw = unwrap(store.todos)
```

Type hints are provided for all public functions and classes.
