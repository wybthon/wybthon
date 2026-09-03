# Stores

Stores hold nested state (dicts and lists) with fine-grained
reactivity: each path through the store is backed by its own signal, so
reading `store.user.name` subscribes only to that leaf. Writes are
**draft-first**, matching SolidJS 2.0: the setter hands you a mutable
draft and you change it with ordinary Python.

## Creating a store

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

[`create_store`][wybthon.create_store] returns `(store, set_store)`,
like `create_signal`.

## Reading values

Read with attribute or item syntax. Reads are tracked per path:

```python
store.count            # 0
store.user.name        # "Ada"
store["user"]["age"]   # 30
store.todos[0].text    # "Learn Wybthon"
len(store.todos)       # tracks the list length
"user" in store        # tracks membership
for todo in store.todos:   # tracks length and each index read
    ...
```

Nested dicts and lists come back as proxies, so reactivity extends to
any depth, and the same path always returns the same proxy object.
Missing keys and out-of-range indices read as `None`.

Proxies deliberately don't expose `.get()`, `.keys()`, `.items()`, or
`.values()`: those names would collide with data keys. Use `[]`, `in`,
`len()`, iteration, or [`snapshot`][wybthon.snapshot] when you need the
plain container.

The store is read-only. `store.count = 5` raises; write through the
setter.

## Writing values

Call `set_store` with a function. It receives a mutable draft; mutate it
with normal Python:

```python
def update(s):
    s.count += 1
    s.user.name = "Grace"
    s.todos[0].done = True
    s.todos.append({"id": 2, "text": "New", "done": False})


set_store(update)

set_store(lambda s: s.user.update({"name": "Jane", "age": 36}))
```

The draft supports:

- attribute and item assignment (`s.name = "x"`, `s.items[0] = "y"`, slice assignment);
- `del s.items[0]` and `del s.key`;
- list methods `append`, `extend`, `insert`, `pop`, `remove`, `clear`, `sort`, and `reverse`;
- dict bulk merge with `s.update({...})`.

Like signal writes, store writes are **staged** and become visible on
the next flush. Draft reads see the latest written values, so a setter
can read what an earlier setter (or an earlier line) wrote. Only the leaf
signals whose values actually changed notify, and however many paths one
draft function touches, subscribers run once per flush.

!!! warning "Return values"
    If the draft function returns a dict or list, that value is merged
    in as replacement state. A bare `lambda s: s.items.pop()` returns
    the popped item; wrap such calls in a `def` that returns `None`.

### Path-style writes with `store_path`

[`store_path`][wybthon.store_path] builds a draft function from a path
and a value (or an updater), for the cases where a lambda reads worse:

```python
from wybthon import store_path

set_store(store_path("user", "address", "city", "Paris"))
set_store(store_path("todos", 0, "done", lambda done: not done))
```

### The write guard

Writing a store inside a tracking scope (a memo body, a single-function
effect, or a hole) raises [`WriteInScopeError`][wybthon.WriteInScopeError]
in dev mode, just as signal writes do. Derive the value with
[`create_projection`][wybthon.create_projection], or write from the
`apply` stage of a split effect, an event handler, or an
[`action`][wybthon.action].

## Reactivity with effects and holes

Store reads inside memos, effects, and holes are tracked automatically:

```python
from wybthon import create_effect, flush

create_effect(lambda: store.count, lambda n: print("Count is:", n))
flush()   # Count is: 0

set_store(lambda s: setattr(s, "count", 10))
flush()   # Count is: 10
```

Only effects that read the changed path re-run. Changing `store.user.name`
doesn't touch an effect that reads only `store.count`.

## Using stores in components

```python
from wybthon import For, component, create_store
from wybthon.html import button, div, p


@component
def TodoApp():
    store, set_store = create_store({"todos": [], "next_id": 1})

    def add_todo(e):
        def update(s):
            s.todos.append({"id": s.next_id, "text": f"Item {s.next_id}", "done": False})
            s.next_id += 1

        set_store(update)

    def toggle(todo_id):
        def flip(s):
            for todo in s.todos:
                if todo.id == todo_id:
                    todo.done = not todo.done

        return lambda e: set_store(flip)

    return div(
        button("Add", on_click=add_todo),
        For(
            lambda: store.todos,
            lambda todo, i: p(
                lambda: f"{'[x]' if todo().done else '[ ]'} {todo().text}",
                on_click=toggle(todo.peek().id),
            ),
            keyed=lambda t: t.id,
        ),
    )
```

The list read `lambda: store.todos` tracks the length and each index, so
appending a todo adds one row. With a key function, each row receives
its item as an accessor; the row's hole reads `todo().done` and
`todo().text` through the store proxy, so toggling one item updates one
text node.

## Reconciling external data

When fresh data arrives from a server, replacing whole subtrees would
notify every subscriber under them. [`reconcile`][wybthon.reconcile]
diffs the new data into the store instead: dicts update key by key, and
lists of dicts are matched by a key (default `"id"`) so unchanged item
objects keep their identity, which is what `For` needs to keep row DOM:

```python
from wybthon import reconcile

set_store(reconcile(fetched_state))               # match list items by "id"
set_store(reconcile(fetched_state, key="uuid"))   # custom key
set_store(reconcile(fetched_state, key=None))     # positional replace
```

The setter also accepts a plain dict or list directly, which merges it
the same way with the default key.

## Snapshots and deep reads

[`snapshot(store)`][wybthon.snapshot] returns the plain data behind a
proxy, untracked. Hand it to `json.dumps`, compare it, or pass it outside
the graph. Mutating it bypasses reactivity; write through the setter
instead.

[`deep(store)`][wybthon.deep] returns a plain *copy* and subscribes the
caller to every nested change. Use it in the compute stage of a split
effect when the whole structure matters:

```python
import json

from wybthon import create_effect, deep, snapshot

create_effect(lambda: deep(store), lambda data: save(json.dumps(data)))

raw = snapshot(store.todos)   # plain list of dicts, no subscription
```

## Derived stores and projections

`create_store(fn, seed)` builds a **derived store**: `fn` runs inside a
render-phase computation, its reads are tracked, and it re-runs when
they change. A function that accepts a draft mutates it in place; a
zero-arg function's return value is reconciled in.

```python
stats, _ = create_store(lambda d: d.update({"total": len(todos())}), {"total": 0})
```

[`create_projection(fn, initial)`][wybthon.create_projection] is the
read-only form. Consumers re-render only for the paths that changed,
which makes projections the right tool for turning a coarse signal into
fine-grained flags:

```python
from wybthon import create_projection, create_signal

selected, set_selected = create_signal(1)

flags = create_projection(
    lambda draft: draft.update({"selected_id": selected()}),
    {"selected_id": None},
)

flags.selected_id   # tracked read
```

[`refresh`][wybthon.refresh] accepts derived stores and projections as
well as memos.

## Optimistic stores

[`create_optimistic_store(source, initial=None)`][wybthon.create_optimistic_store]
creates a store whose writes revert when every in-flight
[`action`][wybthon.action] has settled. `source` is either a tracked
function returning the base state (derived form) or a plain dict or
list (value form). See
[Async and loading](async-loading.md#actions-and-optimistic-state) for
the full pattern.

## Stores versus signals

| | `create_signal` | `create_store` |
| --- | --- | --- |
| **Best for** | Primitive values, simple state | Nested objects, lists |
| **Read** | `count()` | `store.count` |
| **Write** | `set_count(5)` or `set_count(lambda n: n + 1)` | `set_store(lambda s: ...)` |
| **Nested tracking** | Manual (separate signals) | Automatic, per path |
| **Granularity** | Whole value | Per property, index, and length |

## Next steps

- See the [`store`](../api/store.md) API for every helper.
- Read [Reactivity](reactivity.md) for the underlying signal model and flush timing.
- Browse [Authoring patterns](../guides/authoring-patterns.md) for store recipes.
