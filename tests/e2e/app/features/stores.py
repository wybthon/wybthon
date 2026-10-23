"""Reactive stores: per-path tracking and draft-first mutations."""

from wybthon import component, create_store, html


@component
def Page():
    store, set_store = create_store(
        {
            "count": 0,
            "user": {"name": "Ada", "age": 30},
            "todos": [{"text": "first", "done": False}],
        }
    )

    def inc(s):
        s.count += 1

    def rename(s):
        s.user.name = "Grace"

    def toggle(s):
        s.todos[0].done = True

    def add_todo(s):
        s.todos.append({"text": "next", "done": False})

    # Store reads in a template are attribute and item accesses, so each
    # one compiles into a getter that tracks exactly that path.
    return html(t"""
      <div data-testid="page-stores">
        <h2>Stores</h2>
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
