"""Reactive stores: per-path tracking and draft-first mutations."""

from dataclasses import dataclass, field

from wybthon import component, create_store, html


@dataclass
class User:
    name: str
    age: int


@dataclass
class Todo:
    text: str
    done: bool = False


@dataclass
class State:
    count: int = 0
    user: User = field(default_factory=lambda: User("Ada", 30))
    todos: list[Todo] = field(default_factory=lambda: [Todo("first")])


@component
def Page():
    # A dataclass store reads and edits like the dataclass itself.
    store, set_store = create_store(State())
    # A dict store reads with subscripts.
    labels, set_labels = create_store({"title": "Stores"})

    def inc(s: State):
        s.count += 1

    def rename(s: State):
        s.user.name = "Grace"

    def toggle(s: State):
        s.todos[0].done = True

    def add_todo(s: State):
        s.todos.append(Todo("next"))

    # Store reads in a template are attribute and item accesses, so each
    # one compiles into a getter that tracks exactly that path.
    return html(t"""
      <div data-testid="page-stores">
        <h2>{labels["title"]}</h2>
        <p>count: <span data-testid="store-count">{store.count}</span></p>
        <p>name: <span data-testid="store-name">{store.user.name}</span></p>
        <p>todo0 done: <span data-testid="store-todo">{str(store.todos[0].done)}</span></p>
        <p>todos len: <span data-testid="store-len">{len(store.todos)}</span></p>
        <button data-testid="store-inc" onclick={(lambda e: set_store(inc))}>inc count</button>
        <button data-testid="store-rename" onclick={(lambda e: set_store(rename))}>rename</button>
        <button data-testid="store-toggle" onclick={(lambda e: set_store(toggle))}>toggle todo</button>
        <button data-testid="store-add" onclick={(lambda e: set_store(add_todo))}>add todo</button>
      </div>
    """)
