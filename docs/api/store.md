### wybthon.store

::: wybthon.store

#### Public API

##### Store creation

- `create_store(initial) -> (store, set_store)`. Create a reactive store from a dict or list. The `store` is a **read-only fine-grained proxy**: reads track per path, so `store.user.name` subscribes only to that leaf.
- `create_projection(fn, initial=None) -> store`. Read-only **derived store** (Solid's `createProjection`). `fn(draft)` runs in a render effect: reads inside it are tracked, and when a dependency changes `fn` re-runs against the same draft. Because writes go through fine-grained store signals, consumers re-render only for the paths that actually changed. `initial` is the backing state (defaults to an empty dict).
- `create_optimistic_store(source, initial=None) -> (store, set_optimistic)`. Store whose writes are **optimistic**: draft mutations through `set_optimistic` apply immediately, and the store reverts to its base state when every in-flight [`action`][wybthon.action] has settled. `source` may be a tracked function returning the base state (derived form; re-runs and reconciles when its dependencies change, with `initial` as the state before the first run) or a plain dict/list (value form).

##### Store setter (draft-first)

`set_store` takes a **draft function**: it hands your function a mutable
draft of the state, and you mutate it with normal Python. Attribute and
index assignment, `append`, `insert`, `pop`, `remove`, `extend`,
`clear`, `update`, and `del` all work at any depth. Only the leaves
whose values actually changed notify.

```python
store, set_store = create_store({"user": {"name": "Ada"}, "todos": []})

def update(s):
    s.user.name = "Grace"
    s.todos.append({"id": 1, "text": "hi"})

set_store(update)
```

Alternatively, pass a [`reconcile`][wybthon.reconcile] result to diff
external data in:

```python
set_store(reconcile(fetched))
```

Those are the only two calling conventions; anything else raises
`TypeError`.

##### Reconcile and unwrap

- `reconcile(data, key="id")`. Create a reconcile marker for `set_store`: the new data is **diffed** into the existing state so only changed paths notify. List items are matched by `key`, preserving item identity across updates (important for `For`). Pass `key=None` to disable key matching (positional replace).
- `unwrap(value)`. Return the raw data underneath a store proxy without tracking. Plain values pass through unchanged.

```python
set_store(reconcile(fetched_todos))
raw = unwrap(store.todos)
```

##### Optimistic stores

Pair `create_optimistic_store` with actions: mutate the optimistic
store for instant UI, reconcile the real answer into a regular store,
and let the overlay revert when the action settles.

```python
todos, set_todos = create_store({"items": []})

shown, set_shown = create_optimistic_store(lambda: unwrap(todos)["items"], [])

@action
async def add(title):
    set_shown(lambda s: s.append({"title": title, "saving": True}))
    saved = await api_create(title)
    set_todos(lambda s: s.items.append(saved))
```

Type hints are provided for all public functions and classes.
