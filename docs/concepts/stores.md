### Stores

Stores provide reactive state management for nested objects and lists. Inspired by SolidJS `createStore`, they let you work with complex state while maintaining fine-grained reactivity, since each property path is tracked independently.

#### Creating a store

```python
from wybthon import create_store

store, set_store = create_store({
    "count": 0,
    "user": {"name": "Ada", "age": 30},
    "todos": [
        {"id": 1, "text": "Learn Wybthon", "done": False},
    ],
})
```

`create_store` returns a `(store, set_store)` tuple, similar to `create_signal`.

#### Reading values

Access store values via attribute syntax. Reads are reactive: any effect or render function that reads a store property will re-run when that specific property changes:

```python
store.count           # 0
store.user.name       # "Ada"
store.todos[0].text   # "Learn Wybthon"
```

Nested dicts become store proxies and list values become list proxies, so reactivity extends to any depth. Reading `store.user.name` subscribes only to that leaf, not to the entire store.

#### Writing values

Writes are **draft-first**: call `set_store` with a function, and it receives a mutable draft of the state. Mutate the draft with normal Python:

```python
def update(s):
    s.count += 1                     # attribute assignment
    s.user.name = "Grace"            # nested write
    s.todos[0].done = True           # index path
    s.todos.append({"id": 2, "text": "New", "done": False})

set_store(update)

# Small updates read fine as lambdas:
set_store(lambda s: s.user.update({"name": "Jane", "age": 36}))
```

The draft supports:

- Attribute and item assignment (`s.name = "new"`, `s.items[0] = "x"`)
- `del s.items[0]` and `del`-style dict key removal
- List methods: `append`, `insert`, `pop`, `remove`, `extend`, `clear`
- Dict bulk merge: `s.update({...})`

Only the leaves that actually changed notify their subscribers, and because effects run once per flush, a draft function making many writes still produces a single settled update.

The store itself is **read-only**: writing directly via `store.count = 5` raises an error. Always mutate through the setter's draft.

#### Reactivity with effects

Store reads inside `create_effect` and render functions are tracked automatically:

```python
from wybthon import create_effect, flush

create_effect(lambda: print("Count is:", store.count))
# Prints: Count is: 0

set_store(lambda s: setattr(s, "count", 10))
flush()
# Prints: Count is: 10
```

Only effects that read the changed path re-run. Changing `store.user.name` won't re-trigger an effect that only reads `store.count`. In the browser the flush happens automatically; see [Automatic batching](reactivity.md#automatic-batching).

#### Using stores in components

Stores pair naturally with the `@component` decorator:

```python
from wybthon import For, button, component, create_store, div, dynamic, p

@component
def TodoApp():
    store, set_store = create_store({
        "todos": [],
        "next_id": 1,
    })

    def add_todo(e):
        def update(s):
            s.todos.append({"id": s.next_id, "text": f"Item {s.next_id}", "done": False})
            s.next_id += 1
        set_store(update)

    def toggle(idx):
        def flip(s):
            s.todos[idx].done = not s.todos[idx].done
        return lambda e: set_store(flip)

    return div(
        button("Add", on_click=add_todo),
        For(
            each=lambda: list(store.todos),
            children=lambda todo, i: p(
                dynamic(lambda: f"{'[x]' if todo().done else '[ ]'} {todo().text}"),
                on_click=toggle(i()),
            ),
        ),
    )
```

#### Reconciling external data

When fresh data arrives from a server, replacing whole subtrees would
re-run every effect under them. `reconcile` diffs the new data into the
store instead, updating only the paths that actually changed. List items
are matched by a key (default `"id"`) so their proxies keep a stable
identity across updates, which is exactly what `For` needs:

```python
from wybthon import reconcile

set_store(reconcile(fetched_state))               # match list items by "id"
set_store(reconcile(fetched_state, key="uuid"))   # custom key
```

#### Projections

`create_projection(fn, initial=None)` creates a **read-only derived
store**. `fn` receives a mutable draft and runs inside a render effect:
any signals, memos, or other stores it reads become dependencies, and
when they change, `fn` re-runs against the same draft. Consumers get
fine-grained updates for exactly the paths that changed:

```python
from wybthon import create_signal, create_projection

selected, set_selected = create_signal(1)

flags = create_projection(
    lambda draft: draft.update({"selected_id": selected()}),
    {"selected_id": None},
)

flags.selected_id   # tracked read; updates when ``selected`` changes
```

#### Optimistic stores

`create_optimistic_store(source, initial=None)` creates a store whose
writes revert when all in-flight [`action`][wybthon.action]s settle.
`source` may be a tracked function returning the base state (derived
form) or a plain dict/list (value form). See
[Async and Loading](async-loading.md#actions-and-optimistic-state) for
the full pattern.

#### Unwrap

`unwrap(value)` returns the raw data underneath a store proxy (untracked),
for example to serialize it or hand it to a non-reactive API:

```python
from wybthon import unwrap

raw = unwrap(store.todos)   # plain list of dicts
```

#### Stores vs signals

| | `create_signal` | `create_store` |
|---|---|---|
| **Best for** | Primitive values, simple state | Nested objects, lists, complex state |
| **Read** | `count()` (call getter) | `store.count` (attribute access) |
| **Write** | `set_count(5)` | `set_store(lambda s: ...)` (draft mutation) |
| **Nested** | Manual (separate signals) | Automatic (fine-grained proxies) |
| **Granularity** | Entire value | Per-property |

## Next steps

- See the [`store`][wybthon.store] API for `create_store`, `create_projection`, and `reconcile`.
- Read [Reactivity](reactivity.md) for the underlying signal model.
- Browse [Authoring patterns](../guides/authoring-patterns.md) for store recipes.
