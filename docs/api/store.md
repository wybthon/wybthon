### wybthon.store

::: wybthon.store

#### What's in this module

Stores give fine-grained reactive access to nested dicts and lists.
Every path is backed by its own signal, so reading `store.user.name`
subscribes only to that leaf. Writes are **draft-first**: the setter
hands you a mutable draft and you mutate it with ordinary Python. Like
signal writes, store writes are staged until the next flush, and writing
a store inside a tracking scope raises
[`WriteInScopeError`][wybthon.WriteInScopeError] in dev mode.

| Name | Description |
| --- | --- |
| [`create_store`][wybthon.create_store] | `(store, set_store)` from a dict or list; or `create_store(fn, seed)` for a derived store whose `fn` re-runs when its reads change. |
| [`create_projection`][wybthon.create_projection] | Read-only store derived from reactive sources; `fn(draft)` mutates it in place, updated fine-grained. |
| [`create_optimistic_store`][wybthon.create_optimistic_store] | `(store, set_optimistic)` whose writes revert to the base state when in-flight actions settle. |
| [`reconcile`][wybthon.reconcile] | `set_store(reconcile(data, key="id"))`: diff external data in, keeping identity for unchanged items. |
| [`store_path`][wybthon.store_path] | `set_store(store_path("user", "name", "Ada"))`: path-style write helper that returns a draft function. |
| [`snapshot`][wybthon.snapshot] | The plain data behind a proxy, untracked (for `json.dumps`, comparisons, or leaving the graph). |
| [`deep`][wybthon.deep] | Tracked deep read: subscribes to every nested change and returns a plain copy. |

Read proxies support attribute and item access, `in`, `len()`,
iteration, and `==` against plain data; they don't expose `.get()`,
`.keys()`, or `.items()` (those would collide with data keys), so use
`[]`, `in`, or `snapshot()` instead. Drafts additionally support
assignment, `del`, `update`, and the list methods `append`, `extend`,
`insert`, `pop`, `remove`, `clear`, `sort`, and `reverse`.

```python
from wybthon import create_effect, create_store, flush, reconcile, snapshot, store_path

store, set_store = create_store({"user": {"name": "Ada"}, "todos": []})

def edit(s):
    s.user.name = "Grace"
    s.todos.append({"id": 1, "text": "hi", "done": False})

set_store(edit)                                        # draft form
set_store(store_path("todos", 0, "done", lambda d: not d))   # path form
set_store(reconcile({"user": {"name": "Grace"}, "todos": []}, key="id"))
flush()

store.user.name          # "Grace" (tracked read)
"todos" in store         # True
snapshot(store)          # {"user": {"name": "Grace"}, "todos": []}
```

Derived and optimistic stores:

```python
from wybthon import action, create_optimistic_store, create_projection, create_signal, create_store, deep

selected, set_selected = create_signal(1)
flags = create_projection(lambda d: d.update({"selected_id": selected()}), {"selected_id": None})

todos, set_todos = create_store({"items": []})
stats, _ = create_store(lambda d: d.update({"total": len(todos.items)}), {"total": 0})

shown, set_shown = create_optimistic_store(lambda: deep(todos)["items"], [])

@action
async def add(title):
    set_shown(lambda s: s.append({"title": title, "saving": True}))
    saved = await api_create(title)
    set_todos(lambda s: s.items.append(saved))
```

Persist a whole store with a split effect:
`create_effect(lambda: deep(store), lambda data: save(data))` re-runs on
any nested write and hands the apply stage a plain copy.

#### See also

- [`action`][wybthon.action], [`create_optimistic`][wybthon.create_optimistic], [`refresh`][wybthon.refresh]
- [Concepts: Stores](../concepts/stores.md)
- [Concepts: Reactivity](../concepts/reactivity.md)
