### Stores

Stores provide reactive state management for nested objects and lists. Inspired by SolidJS `createStore`, they let you work with complex state while maintaining fine-grained reactivity — each property path is tracked independently.

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

Access store values via attribute syntax. Reads are reactive — any effect or render function that reads a store property will re-run when that specific property changes:

```python
store.count           # 0
store.user.name       # "Ada"
store.todos[0].text   # "Learn Wybthon"
```

Nested dicts become store proxies and list values become list proxies, so reactivity extends to any depth.

#### Writing values

Use the `set_store` setter with a **path-based API**:

```python
# Simple set
set_store("count", 5)

# Functional update
set_store("count", lambda c: c + 1)

# Nested path
set_store("user", "name", "Jane")

# Path through list index
set_store("todos", 0, "done", True)

# Replace an entire nested object
set_store("user", {"name": "Grace", "age": 35})

# Replace an entire list
set_store("todos", [])
```

The store is **read-only** — writing directly via `store.count = 5` raises an error. Always use `set_store`.

#### Produce

For batch mutations, `produce` provides an Immer-style API. The function receives a mutable draft:

```python
from wybthon import produce

# Single mutation
set_store(produce(lambda s: setattr(s, "count", s.count + 1)))

# List mutations
set_store(produce(lambda s: s.todos.append({"id": 2, "text": "New", "done": False})))

# Multiple mutations in one pass
def update(s):
    s.count = 42
    s.user.name = "Updated"

set_store(produce(update))
```

The draft supports:

- Attribute read/write (`s.name`, `s.name = "new"`)
- Item read/write (`s.items[0]`, `s.items[0] = "x"`)
- `append` and `pop` for lists

#### Reactivity with effects

Store reads inside `create_effect` and render functions are tracked automatically:

```python
from wybthon import create_effect

create_effect(lambda: print("Count is:", store.count))
# Prints: Count is: 0

set_store("count", 10)
# Prints: Count is: 10
```

Only effects that read the changed path re-run. Changing `store.user.name` won't re-trigger an effect that only reads `store.count`.

#### Using stores in components

Stores pair naturally with the `@component` decorator:

```python
from wybthon import For, button, component, create_store, div, dynamic, p, produce

@component
def TodoApp():
    store, set_store = create_store({
        "todos": [],
        "next_id": 1,
    })

    def add_todo(e):
        def update(s):
            s.todos.append({"id": s.next_id, "text": f"Item {s.next_id}", "done": False})
            s.next_id = s.next_id + 1
        set_store(produce(update))

    def toggle(idx):
        return lambda e: set_store("todos", idx, "done", lambda d: not d)

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

#### Stores vs signals

| | `create_signal` | `create_store` |
|---|---|---|
| **Best for** | Primitive values, simple state | Nested objects, lists, complex state |
| **Read** | `count()` (call getter) | `store.count` (attribute access) |
| **Write** | `set_count(5)` | `set_store("count", 5)` |
| **Nested** | Manual (separate signals) | Automatic (path-based) |
| **Granularity** | Entire value | Per-property |
