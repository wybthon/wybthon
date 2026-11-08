# Stores

A store holds nested state you read like ordinary data and edit through a draft. Reads in a tracking scope subscribe to exactly what they read, so changing one field of one row reruns only what reads that field. A store wraps a dataclass instance, a dict, or a list, and its view is typed as that same type.

```python
from dataclasses import dataclass, field

from wybthon import create_store, flush


@dataclass
class Todo:
    id: int
    title: str
    done: bool = False

    def toggle(self) -> None:
        self.done = not self.done


@dataclass
class State:
    filter: str = "all"
    todos: list[Todo] = field(default_factory=list)


state, set_state = create_store(State(todos=[Todo(1, "Build a Python UI")]))


def add(draft: State) -> None:
    draft.todos.append(Todo(2, "Test it in the browser"))
    draft.todos[0].toggle()


set_state(add)
flush()
assert state.todos[0].done
assert state.todos[1].title == "Test it in the browser"
```

`state` is typed as `State`, so pyright and mypy check `state.todos[0].title` with no plugin, and the setter takes a `Callable[[State], object]`. Solid's `createStore` works the same way: its store is typed as the object you gave it.

## Dataclass stores

A dataclass store reads its fields as tracked attributes. The dataclass's methods and properties work too, reading through the store, so a property like `label` below is reactive wherever it's read:

```python
@dataclass
class Todo:
    id: int
    title: str
    done: bool = False

    @property
    def label(self) -> str:
        return f"{self.title} (done)" if self.done else self.title
```

A `functools.cached_property` is computed on each read instead of cached, so it stays reactive too.

In a setter, the draft is an instance of the same class: assign fields, call mutating methods, or set properties that have setters. Assigning a name that isn't a field (or a property with a setter) raises `AttributeError`. `isinstance(state, State)` is true, and `snapshot(state)` and `deep(state)` return real `State` instances. The `dataclasses` helpers (`asdict`, `replace`, and `fields`) need a real instance, so call them on `snapshot(state)`.

Replacement data for a dataclass container can be an instance of the same class or a plain mapping, such as decoded JSON: `set_state(reconcile({"filter": "done", "todos": [...]}))` merges into the existing `State` and its nested dataclasses. An instance of a different dataclass raises `TypeError`; to change a nested value's class, assign it from its parent.

Nested dataclasses, dicts, and lists are stores of their own kind. Other values (strings, numbers, tuples, and anything else) are stored as they are. Tuples are immutable values: replace one to change it, as in `draft.tags = (*draft.tags, "new")`.

## Dict and list stores

A dict store implements `Mapping`, and a list store implements `Sequence`: read them with subscripts, iteration, `len`, `in`, and the usual methods such as `.get()`, `.items()`, and `.keys()`. Dict stores have no attribute access, so data keys never collide with method names: a key named `items` is just `state["items"]`. Use a dataclass when you want attributes.

```python
config, set_config = create_store({"theme": {"accent": "blue"}, "rows": []})
config["theme"]["accent"]  # "blue"
config.get("missing", "default")  # tracked, even when absent
set_config(lambda draft: draft["rows"].append({"id": 1}))
```

Missing keys raise `KeyError` and missing indices raise `IndexError`. `get(key, default=None)` doesn't raise, and it's tracked either way, so a computation reading `state.get(row_id)` reruns when that key appears.

For type checking, give a dict store a `TypedDict` type: `create_store(initial)` with `initial: Person` returns a store typed as `Person`.

## Drafts

A setter receives a draft: a mutable view with the store's own type. Dict drafts implement `MutableMapping` and list drafts implement `MutableSequence`, so assignment, deletion, `update`, `append`, `extend`, `insert`, `pop`, slices, `reverse`, and `sort` all work; list drafts also have `move(start, target, count=1)`. A draft and every nested draft expire when the callback returns. Using one afterward raises `DraftExpiredError`.

A setter's `edit()` is the same callback written inline, as a `with` block, so a handler that changes several fields needs no nested function. The draft's changes stage together when the block ends:

```python
def rename(index: int, title: str) -> None:
    with set_state.edit() as draft:
        draft.todos[index].title = title
        draft.todos[index].done = False
```

A callback or block that raises leaves the store unchanged: every edit it made is discarded. Return `None` after mutating, or return replacement data to replace the draft's contents; don't accidentally return the result of `pop`. Passing data instead of a callback replaces the store's contents: `set_state(State())`. Async setters are rejected. Await external work in an action, then make a synchronous edit.

The store takes ownership of the data you give it, and it never mutates that data: a container is copied the first time a setter edits it. Don't keep mutating an object after you've passed it to `create_store` or written it into a draft.

## Versions and subscriptions

A setter stages its edits without changing what reads see. Before a flush, ordinary reads keep seeing the previous version, even for a key that has never been read. During a held transition, the previous version stays visible until the transition reveals. Actions see their own staged edits.

Field reads, membership, list length, mapping keys, and subtree versions are separate dependencies. Changing a sibling subtree doesn't rerun an effect that reads `deep(state.user)`. Negative list indices also track length.

```python
from wybthon import create_effect, deep

create_effect(lambda: state.todos[0].title, print)
create_effect(lambda: deep(state.todos), print)
```

`snapshot(value)` returns detached plain data (or dataclass instances) without tracking; changing the snapshot can't change the store. `deep(value)` does the same and subscribes to that whole subtree.

## Lazy wrapping

Creating a store does no work proportional to its size. A nested container gets its reactive bookkeeping the first time something reads it, so a store of 10,000 rows is created in constant time, and a large replacement written into a draft costs only what's later read. A container that's never read is never wrapped, and `snapshot` copies it directly.

## Shallow stores

`create_store(initial, shallow=True)` makes only the top level reactive. Nested values are stored and returned as they are, plain dicts, lists, and objects, so replacing one is the way to change it:

```python
config, set_config = create_store({"theme": {"accent": "blue"}}, shallow=True)
set_config(lambda draft: draft.update(theme={"accent": "red"}))
```

Use a shallow store for large values you replace wholesale, such as an API response. Don't mutate a value you read from one.

## Identity and reconciliation

Pass a store list straight to [`For`][wybthon.For]: `For(state.todos, row)`. A store list is already reactive, and `For` applies its edits incrementally: appending, removing, swapping, and editing rows never rescans the list. Default matching preserves entity identity, so `row` receives each entity's store and an index accessor; read fields in the template (`{todo.title}`) to track them. Use `keyed=lambda todo: todo.id` when replacement objects represent the same application entity; with a key function, `row` receives item and index accessors instead (`todo().title`).

```python
from wybthon import reconcile

set_state(reconcile(State(todos=[Todo(2, "Updated"), Todo(1, "Build a Python UI")]), key="id"))
```

`key` names the identifying field (`"id"` by default) or is a function computing the identity from an entity, such as `key=lambda row: (row["kind"], row["id"])`. Keyed reconciliation updates matching entities in place and matches duplicate keys in occurrence order. `key=None` replaces list entities positionally. Moving an existing entity within a draft (assigning `draft.todos[0]` somewhere else) keeps its identity.

## Derived and optimistic stores

`create_projection(fn, seed)` and `create_store(fn, seed)` derive a read-only store from tracked reads. The callback may return data or mutate the draft it's given. It can await work or yield values from an async generator. Draft changes publish atomically when that result is ready.

```python
from wybthon import create_projection, is_pending, refresh


async def load_user():
    return await fetch_user(user_id())


user = create_projection(load_user, {"name": ""})
# Read user["name"] inside Loading content.
busy = lambda: is_pending(lambda: user["name"])
# In an async handler: await refresh(user)
```

Errors surface when the projection is read, so `Errored` handles them. Refresh is quiet and awaitable. Disposing the owner cancels the producer.

A projection also replaces a selection helper. Because it notifies only the keys that change, selecting a different row updates two rows, not every row:

```python
from wybthon import For, create_projection, create_signal, html

selected, set_selected = create_signal(None)
is_selected = create_projection(lambda: {} if selected() is None else {selected(): True})


def row(todo, i):
    def select():
        set_selected(todo.id)

    return html(t"""
      <tr class={"active" if is_selected.get(todo.id) else None} onclick={select}>
        <td>{todo.title}</td>
      </tr>
    """)


html(t"<table><tbody>{For(state.todos, row)}</tbody></table>")
```

`create_optimistic_store(source, seed)` returns a store and an optimistic draft setter. Active edits replay over new authoritative data, and each action's edits disappear when its dependency group settles. Keep draft callbacks deterministic. See [Runtime contracts](runtime-contracts.md) for concurrent action, acknowledgment, and cancellation semantics.
