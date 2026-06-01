"""Reactive stores: per-path tracking, nested updates, functional set, and produce."""

from app.testkit import tid

from wybthon import button, component, create_store, div, dynamic, h2, p, produce, span


@component
def Page():
    store, set_store = create_store(
        {
            "count": 0,
            "user": {"name": "Ada", "age": 30},
            "todos": [{"text": "first", "done": False}],
        }
    )

    return div(
        h2("Stores"),
        p("count: ", span(dynamic(lambda: str(store.count)), **tid("store-count"))),
        p("name: ", span(dynamic(lambda: store.user.name), **tid("store-name"))),
        p("todo0 done: ", span(dynamic(lambda: str(store.todos[0].done)), **tid("store-todo"))),
        p("todos len: ", span(dynamic(lambda: str(len(store.todos))), **tid("store-len"))),
        button("inc count", on_click=lambda e: set_store("count", lambda c: c + 1), **tid("store-inc")),
        button("rename", on_click=lambda e: set_store("user", "name", "Grace"), **tid("store-rename")),
        button("toggle todo", on_click=lambda e: set_store("todos", 0, "done", True), **tid("store-toggle")),
        button(
            "produce inc",
            on_click=lambda e: set_store(produce(lambda s: setattr(s, "count", s.count + 1))),
            **tid("store-produce"),
        ),
        button(
            "add todo",
            on_click=lambda e: set_store(produce(lambda s: s.todos.append({"text": "next", "done": False}))),
            **tid("store-add"),
        ),
        **tid("page-stores"),
    )
