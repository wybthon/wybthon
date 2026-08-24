"""Reactive stores: per-path tracking and draft-first mutations."""

from app.testkit import tid

from wybthon import button, component, create_store, div, dynamic, h2, p, span


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

    return div(
        h2("Stores"),
        p("count: ", span(dynamic(lambda: str(store.count)), **tid("store-count"))),
        p("name: ", span(dynamic(lambda: store.user.name), **tid("store-name"))),
        p("todo0 done: ", span(dynamic(lambda: str(store.todos[0].done)), **tid("store-todo"))),
        p("todos len: ", span(dynamic(lambda: str(len(store.todos))), **tid("store-len"))),
        button("inc count", on_click=lambda e: set_store(inc), **tid("store-inc")),
        button("rename", on_click=lambda e: set_store(rename), **tid("store-rename")),
        button("toggle todo", on_click=lambda e: set_store(toggle), **tid("store-toggle")),
        button("add todo", on_click=lambda e: set_store(add_todo), **tid("store-add")),
        **tid("page-stores"),
    )
