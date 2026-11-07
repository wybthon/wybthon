# RFC 0007: Engine v7: stores typed by your own data

- **Status:** Implemented
- **Author:** Owen Carey
- **Created:** 2026-11-06

## Summary

Rebuild stores so they cost little more than the signals they're made of, and type them as the data they hold. Stores are how Solid 2.0 holds collections, and they were the slowest and least Pythonic part of Wybthon: reads were typed `Any`, only dicts and lists were supported, and attribute access on dict keys collided with mapping methods. Engine v7 changes five things:

1. **Lazy wrapping.** Creating a store is constant time. A nested container gets its reactive bookkeeping the first time something reads it.
2. **Copy-on-write containers that are signals.** Each container is a signal of its own data. A setter copies a container the first time it edits it and stages the copy; a held transition keeps showing the old container. The persistent vector is gone.
3. **Dataclass stores, typed as the dataclass.** `create_store(State(...))` returns a view typed as `State`, whose fields, methods, and properties work reactively. Every store is typed as its own data, as Solid's `Store<T>` is.
4. **Subscripts for dict stores.** Dict stores lose attribute access; data keys are read with `[]`, so they never collide with method names.
5. **Shallow stores.** `create_store(initial, shallow=True)` makes only the top level reactive.

Signals, the reactive core, the renderer, and the kernel are unchanged. Every store contract in [Runtime contracts](../concepts/runtime-contracts.md) holds as it did.

## Motivation

### Solid 2.0 is still a release candidate

npm's `latest` is still `solid-js@1.9.18`, and `next` is `2.0.0-rc.21`, which [Engine v6](0006-engine-v6.md) already targets. API parity isn't the gap.

### Stores were the slow path

[Engine v6](0006-engine-v6.md#alternatives-considered) left store writes for "a redesign of its own." Measured on an Apple M-series laptop with Chromium 151 and Pyodide 314.0.6, the benchmark table's store mode was slower than its signal mode on every operation that creates or updates rows:

| Operation (v6, sync commit) | Signal mode | Store mode |
| --- | ---: | ---: |
| Create 10,000 rows | 120.8 ms | 193.3 ms |
| Update every tenth row | 3.8 ms | 10.9 ms |
| Create 1,000 rows | 12.6 ms | 18.8 ms |

Natively, creating a 10,000-row store took 15.5 ms against about 1 ms to build the dicts, and a field write cost about three times a signal write. Profiles pointed at two causes. Every nested container was encoded into a node with its own `Signal` when the store was created, whether or not anything read it. And every edit produced a new persistent version: a copied dict, or a new path through a 32-way persistent vector, wrapped in a new state record.

This matters more than the table suggests. The fast signal mode stores a hand-made label signal in every row, which real applications don't write; the idiomatic Solid 2.0 program holds its rows in a store. The benchmark's headline numbers flattered the engine.

### Stores weren't Pythonic

A store's reads were typed `Any`. `create_store` accepted only dicts and lists, so application state couldn't be a dataclass, the most Pythonic way to describe it. And attribute access on dict keys, the idiom the docs used, broke for any key named like a mapping method: `state.items` was the method, not the data.

## Design

### 1. Lazy wrapping

A store node starts as a shell around the raw data it was given. The first read copies that data into the node's own container, wrapping each nested container in a shell of its own. Creating a store allocates one shell, whatever its size; reading a 10,000-row list allocates 10,000 shells but no row's fields; and writing a large replacement into a draft wraps none of it until it's read. A container that's never read is never wrapped, and `snapshot` copies its raw data directly.

Because a node copies its data when it's first read, a store never mutates the data it was given. Nested containers are wrapped as they're reached, so every version of a parent (committed, staged, and held) holds the same child node, and an entity's identity is fixed from the first read.

### 2. Containers are copy-on-write signals

A node is a `Signal` whose value is its container's data: a dict for a dict or a dataclass, and a list for a list. The reactive core's existing machinery does the rest:

- **Staging.** A setter's session copies a container the first time it edits it, edits the copy, and when the callback returns, stages it with the node's ordinary signal write. Reads keep seeing the committed container until the flush commits the new one, which is the contract that before a flush, reads see the previous version, even for a key that has never been read.
- **Holding.** When a transition holds a node, the core keeps its previous value, and that value is the previous container, which nothing ever mutates. Reads outside the graph see it until the transition reveals. There are no per-version records and no persistent vector.
- **Atomicity.** A callback that raises discards its copies; nothing was staged.
- **Fields.** A field read in a tracking scope creates a property signal caused by its node, released when its last observer leaves, as in Engine v6. A setter doesn't stage each field it changes: it records the changed keys on the node, and the node's commit publishes them with the node's own origin and transition. Under an action, a read goes through the node's staged version, so the action sees its own edits.
- **Lists.** A list version carries a revision number, and each staged edit appends a record (set, splice, clear, or reset) to the node's history, so `For` keeps its incremental paths: appending, removing, swapping, and editing rows never rescans the list.

A container is copied once per setter that edits it. For a row, that's a handful of fields. For a 10,000-row list, a structural edit copies the list's 10,000 references once, which costs about 0.2 ms in the browser; the persistent vector avoided that copy by paying a Python-level tree path on every read and write.

Parent links are weak and shared: every child of a container holds the same callback-free weak reference to it, so a row a component keeps doesn't keep its list alive. A setter pauses the cyclic collector for its duration, as a flush does, because it allocates in a burst that outlives it.

### 3. Dataclass stores

`create_store` accepts a dataclass instance as well as a dict or a list, and nested dataclasses become stores of their own:

```python
@dataclass
class Todo:
    id: int
    title: str
    done: bool = False

    def toggle(self) -> None:
        self.done = not self.done


state, set_state = create_store(State(todos=[Todo(1, "Write")]))
state.todos[0].title            # a tracked read, typed `str`
set_state(lambda d: d.todos[0].toggle())
```

The view (`StoreObject`) reads fields as tracked attributes and resolves every other name on the dataclass, binding methods and properties to the view. A property is therefore reactive wherever it's read, and a method called on a draft edits the draft. The view reports the dataclass as its `__class__`, so `isinstance(state, State)` and class patterns in `match` work. A draft assigns fields and properties that have setters, and rejects anything else. `snapshot` and `deep` build real instances of the dataclass, without calling `__init__`.

### 4. Typing

Every store is typed as its own data:

```python
def create_store[T](initial: T, seed: None = None, *, shallow: bool = False) -> tuple[T, StoreSetter[T]]: ...
```

`StoreSetter[T]` accepts `Callable[[T], object]`, replacement data `T`, or a `reconcile` result. `snapshot`, `deep`, and `create_projection` return `T`. A dataclass store type-checks as the dataclass, and a dict store with a `TypedDict` type checks its keys, with no plugin for mypy or pyright. Solid types its stores the same way.

The view is read-only at runtime even though its static type is the mutable `T`, as in Solid, where `Store<T>` is `T`. Writing to it raises.

### 5. Dict stores use subscripts

A dict store reads its keys with `[]`, and attribute access raises `AttributeError` with a hint to use a subscript or a dataclass. Data and methods never collide, and dict stores behave exactly like the read-only mappings they implement. Attribute access belongs to the type that declares attributes: the dataclass.

### 6. Shallow stores

`shallow=True` keeps nested values as they are: the root container is reactive, and its values are stored and returned unwrapped. Use it for large values replaced wholesale, such as API responses.

### 7. Projections and optimistic stores

`create_projection`, derived `create_store`, `create_optimistic_store`, `reconcile`, `snapshot`, and `deep` run on the new core unchanged in behavior. An optimistic store's authoritative view records a container's committed data when it's first read, so lazily wrapped containers keep their authoritative version.

### Clearing large lists

Clearing a 10,000-row table takes about 75 ms of synchronous commit in store mode and 57 ms in signal mode, about 27 ms of it in the kernel. A spike in Chromium found that the kernel's release walk isn't the bottleneck: walking the removed rows' DOM to find their ids costs the same 5 to 7 ms as iterating the ids directly, almost all of it `Map` deletions, and the browser's own removal of 10,000 rows takes about 12 ms. Releasing ids by range would save nothing, so the kernel is unchanged. The Python side disposes each row's owner and bindings, which the store rewrite doesn't change.

## Results

See [Engine v7 benchmark results](https://github.com/wybthon/wybthon/blob/main/benchmarks/results/engine-v7.md) for the full tables. In the browser, store mode against Engine v6:

| Operation (sync commit) | v6 | v7 | Change |
| --- | ---: | ---: | ---: |
| Create 1,000 rows | 18.8 ms | 15.6 ms | -17% |
| Replace 1,000 rows | 24.0 ms | 21.9 ms | -9% |
| Create 10,000 rows | 193.3 ms | 150.5 ms | -22% |
| Update every tenth row | 10.9 ms | 7.4 ms | -32% |
| Remove a row | 3.2 ms | 2.6 ms | -19% |
| Append 1,000 rows | 21.0 ms | 16.9 ms | -20% |
| Swap two rows | 0.4 ms | 0.6 ms | +0.2 ms |
| Clear 10,000 rows | 75.2 ms | 75.0 ms | 0% |

Signal mode is unchanged within noise. Store mode now trails signal mode by 25% to create 10,000 rows (from 60%) and takes about twice as long to update every tenth row (from about three times), while swapping and removing rows remain much faster in store mode, which edits the list in place instead of replacing it.

The targets set when this work was proposed were a field write within 1.3 times a signal write and store mode within 10% of signal mode on create and update. Neither is met. Natively, a field write now costs about 2.8 times a signal write (from about 3.9 times): a setter builds a draft view for each container it reaches, copies each container it edits, and a read through a store list reads two fields where the signal benchmark reads one. Closing the rest of the gap would mean edits that skip drafts, which is a different API.

## Breaking changes

- Dict stores and their drafts no longer support attribute access: `state.user.name` is `state["user"]["name"]`, and `draft.count = 1` is `draft["count"] = 1`.
- `Draft` and `DraftList` are no longer exported. A setter's draft is typed as the store's own type.
- `create_store`, `create_projection`, `snapshot`, and `deep` return the type of the data they're given instead of `Store[S]`, `StoreList[T]`, or `Any`.
- `wybthon._vector` is removed.
- A list store's internal state (`_wyb_list_state()`) returns the items, which carry their revision, instead of a `(data, revision)` record.
- Cyclic initial data isn't detected when a store is created; it's still unsupported.

## Alternatives considered

**Mutating containers in place with undo records.** A setter could edit the committed container in place and keep, for a held transition, only the old values of the keys it changed. That avoids copying a container per setter, but a read before the flush must still see the old value of a key that was never read, so every read would consult a staged overlay, and every held transition would need its own undo chain. Copying a row's few fields once per setter is cheaper than either, and the old container serves as the held version for free.

**Keeping the persistent vector.** It made a structural edit of a 10,000-row list O(log n) instead of O(n), but every read and write paid a Python-level tree walk. A plain list copy is a single C-level operation, about 0.2 ms for 10,000 rows in the browser.

**Keeping attribute access on dict keys.** It reads well, but it can't be typed (a `TypedDict` has no attributes), and it fails silently for keys named like methods. Dataclasses give attribute access with types.

**Proxying arbitrary classes.** Supporting any object with a `__dict__` would make `create_store(SomeClass())` work for classes that weren't designed to be data, including ones whose methods have side effects. Dataclasses declare their fields, so the store knows exactly what to track. Other classes are stored as opaque values.

**Reporting `list` as a list store's `__class__`.** A dataclass view reports its dataclass so `isinstance` checks work, but the renderer and the framework check `isinstance(value, list)` to flatten children and coerce values, and a list store must not be mistaken for a plain list there.

## Unresolved questions

- Store mode still trails signal mode on creating and updating rows. Edits that skip drafts would close more of the gap.
- Clearing 10,000 rows is bounded by per-row disposal in Python and native DOM removal.
- Pydantic models and attrs classes could be supported the way dataclasses are, through their field declarations.
