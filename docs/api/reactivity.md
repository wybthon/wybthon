### wybthon.reactivity

::: wybthon.reactivity

#### Ownership classes

##### `Owner`

Base reactive ownership scope.  Tracks child owners and cleanup callbacks.

| Attribute | Description |
|-----------|-------------|
| `_parent` | Parent `Owner` or `None` for roots. |
| `_children` | List of child `Owner` instances. |
| `_cleanups` | Callbacks run on disposal (LIFO order). |
| `_context_map` | Optional dict mapping context IDs to values (used by `Provider`). |

| Method | Description |
|--------|-------------|
| `dispose()` | Dispose children depth-first, run own cleanups, detach from parent. |
| `_lookup_context(ctx_id, default)` | Walk up the owner chain to find a context value. |
| `_set_context(ctx_id, value)` | Store a context value on this owner. |

##### `Computation(Owner)`

Reactive computation that tracks `Signal` reads and re-runs when they
change.  Also an ownership scope: child computations created during
execution are disposed before each re-run.

| Method | Description |
|--------|-------------|
| `run()` | Dispose children and cleanups, clear deps, re-execute the function under `_current_owner = self`. |
| `schedule()` | Enqueue a re-run on the next flush. |
| `dispose()` | Cancel subscriptions, clear deps, remove from pending queue, run cleanups. |

#### Public API

##### Signals-first API (recommended)

- `create_signal(value) -> (getter, setter)`
- `create_effect(fn) -> Computation` — the returned `Computation` is added as a child of the current owner.  Inside a component's setup phase the owner is the `_ComponentContext` (effect survives re-renders, disposed on unmount).  Inside a render function the owner is the render `Computation` (effect disposed on re-render).  Supports previous value: `create_effect(lambda prev: ...)`.
- `create_memo(fn) -> getter` — creates a `Computation` under the current owner; disposed when the owner is disposed.
- `on_mount(fn)` — run after first render
- `on_cleanup(fn)` — appends `fn` to the current owner's cleanup list.  Inside `create_effect`: runs before each re-execution and on disposal.  Inside a component's setup phase: runs when the component unmounts.
- `batch() -> context manager` or `batch(fn) -> result` — callback form flushes synchronously

##### Resources

- `create_resource(fetcher) -> Resource`
- `create_resource(source, fetcher) -> Resource` — refetches when source changes

##### Reactive utilities

- `untrack(fn)` — run without tracking signal reads
- `on(deps, fn, defer=False)` — effect with explicit deps
- `create_root(fn)` — creates an independent `Owner` root.  `fn` receives a `dispose` callback that tears down the root and all its children.  Effects created inside the root are owned by it and cleaned up on `dispose()`.
- `merge_props(*sources)` — merge prop dicts
- `split_props(props, *key_groups)` — split props by key name

##### Global state

A single `_current_owner` global tracks the active ownership scope.
When a `Computation.run()` executes, it sets `_current_owner = self` so
that any effects or memos created during execution become its children.

Type hints are provided for all public functions and classes.
