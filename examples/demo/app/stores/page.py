from wybthon import For, button, component, create_store, div, dynamic, h, h2, h3, p, produce, span


@component
def TodoStore():
    store, set_store = create_store(
        {
            "todos": [
                {"id": 1, "text": "Learn Wybthon", "done": True},
                {"id": 2, "text": "Build an app", "done": False},
            ],
            "next_id": 3,
        }
    )

    def add_todo(e):
        def update(s):
            s.todos.append({"id": s.next_id, "text": f"Todo #{s.next_id}", "done": False})
            s.next_id = s.next_id + 1

        set_store(produce(update))

    def toggle(idx):
        return lambda e: set_store("todos", idx, "done", lambda d: not d)

    def remove(idx):
        return lambda e: set_store("todos", lambda ts: [t for i, t in enumerate(ts) if i != idx])

    def summary() -> str:
        todos = list(store.todos)
        done = sum(1 for t in todos if t.done)
        return f"{len(todos)} items, {done} done"

    return div(
        h3("Todo List (create_store + produce)"),
        p(dynamic(summary)),
        For(
            each=lambda: list(store.todos),
            children=lambda item, idx: div(
                span(
                    dynamic(lambda: f"{'[x]' if item().done else '[ ]'} {item().text}"),
                    on_click=toggle(idx()),
                    style=lambda: {
                        "cursor": "pointer",
                        "textDecoration": "line-through" if item().done else "none",
                    },
                ),
                button(
                    "x",
                    on_click=remove(idx()),
                    style={"marginLeft": "8px", "fontSize": "0.8rem"},
                ),
                style={"display": "flex", "alignItems": "center", "gap": "4px", "padding": "4px 0"},
            ),
        ),
        button("Add todo", on_click=add_todo),
        class_="demo-section",
    )


@component
def NestedStore():
    store, set_store = create_store(
        {
            "user": {"name": "Ada Lovelace", "role": "Engineer"},
            "settings": {"theme": "dark", "notifications": True},
        }
    )

    def toggle_theme(e):
        set_store("settings", "theme", lambda t: "light" if t == "dark" else "dark")

    def toggle_notifications(e):
        set_store("settings", "notifications", lambda n: not n)

    def rename(e):
        set_store("user", "name", lambda n: "Grace Hopper" if n == "Ada Lovelace" else "Ada Lovelace")

    return div(
        h3("Nested State (path-based setter)"),
        p(dynamic(lambda: f"User: {store.user.name} ({store.user.role})")),
        p(dynamic(lambda: f"Theme: {store.settings.theme}")),
        p(dynamic(lambda: f"Notifications: {'on' if store.settings.notifications else 'off'}")),
        div(
            button("Toggle theme", on_click=toggle_theme),
            button("Toggle notifications", on_click=toggle_notifications),
            button("Swap name", on_click=rename),
            style={"display": "flex", "gap": "8px", "flexWrap": "wrap"},
        ),
        class_="demo-section",
    )


@component
def Page():
    return div(
        div(
            h2("Stores"),
            p("Reactive state management for nested objects and lists, inspired by SolidJS createStore."),
            class_="page-header",
        ),
        h(TodoStore, {}),
        h(NestedStore, {}),
        class_="page",
    )
