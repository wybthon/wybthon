# Stores

Stores are read-only reactive mappings and sequences. Update them with a synchronous, scoped draft. Containers have entity identity: moving a row changes its position without changing which object its proxy represents.

```python
from wybthon import create_store, flush, snapshot

state, write = create_store({
    "user": {"name": "Ada"},
    "items": [{"id": 1, "title": "Build a Python UI"}],
})

def edit(draft):
    draft.user.name = "Grace"
    draft["items"].append({"id": 2, "title": "Test it in the browser"})

write(edit)
flush()
assert state.user.name == "Grace"
```

## Collection protocols

`Store` implements `Mapping`, and `StoreList` implements `Sequence`. Use indexing, iteration, `len`, membership, and ordinary mapping methods such as `.get()`, `.items()`, and `.keys()`. Attribute access is convenient for nonconflicting string keys. A key named `items` is `state["items"]`; `state.items()` is the mapping method. Missing entries raise ordinary Python exceptions.

Drafts implement `MutableMapping` and `MutableSequence`. Use assignment, deletion, `update`, `append`, `extend`, `insert`, `pop`, slices, `reverse`, and `sort` as appropriate. A draft and every nested draft expire when the callback returns. Escaped reads or writes raise `DraftExpiredError`.

A callback that raises leaves the published store unchanged. Return `None` after mutations. Returning replacement mapping or sequence data replaces the draft contents; don't accidentally return the result of `pop` or a tuple of mutations. Async setters are rejected. Await external work in an action, then perform a synchronous draft edit.

## Versions and subscriptions

Successful edits stage versions without changing the revealed data. Before a flush, ordinary reads keep seeing the previous version, even for a key that has never been read. During held transitions the previous version remains visible until reveal. Actions see their own staged edits.

Property reads, membership, list length, mapping keys, and subtree versions have separate dependencies. Changing a sibling subtree doesn't rerun an effect that reads `deep(state.user)`. Negative list indices also track length.

```python
from wybthon import create_effect, deep

create_effect(lambda: state.user.name, print)
create_effect(lambda: deep(state.user), lambda user: print(user))
```

`snapshot(value)` returns detached plain data without tracking. Changing the snapshot can't change the store. `deep(value)` returns detached plain data and subscribes to that subtree. Neither exposes mutable backing data.

## Identity and reconciliation

`For(lambda: state["items"], row)` can use store edit records directly. Default matching preserves entity identity. Use `keyed=lambda item: item.id` when replacement objects represent the same application entity; that callback receives item and index accessors.

```python
from wybthon import reconcile

write(reconcile({"user": {"name": "Grace"}, "items": [
    {"id": 2, "title": "Updated"},
    {"id": 1, "title": "Build a Python UI"},
]}, key="id"))
```

Keyed reconciliation updates matching entities in place and matches duplicate keys in occurrence order. `key=None` replaces list entities. Store drafts preserve entities when moving existing proxies. Initial cyclic input isn't supported.

## Derived and optimistic stores

`create_projection(fn, seed)` and `create_store(fn, seed)` derive a read-only store from tracked reads. The callback may return data or mutate a draft argument. It can await work or yield values from an async generator. Draft changes publish atomically when that result is ready.

```python
from wybthon import create_projection, is_pending, refresh

async def load_user():
    return await fetch_user(user_id())

user = create_projection(load_user, {"name": ""})
# Read user.name inside Loading content.
busy = lambda: is_pending(lambda: user.name)
# In an async handler: await refresh(user)
```

Errors surface when the projection is read, so `Errored` handles them. Refresh is quiet and awaitable. Disposing the owner cancels the producer.

`create_optimistic_store(source, seed)` returns a store and an optimistic draft setter. Active edits replay over new authoritative data, then disappear when the shared action transition settles. Keep draft callbacks deterministic. See [Runtime contracts](runtime-contracts.md) for concurrent action, acknowledgment, and cancellation semantics.
