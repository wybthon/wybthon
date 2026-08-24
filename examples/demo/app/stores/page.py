from wybthon import For, button, component, create_store, div, dynamic, h, h2, h3, p, span, unwrap


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

        set_store(update)

    def toggle(idx):
        def update(s):
            s.todos[idx].done = not s.todos[idx].done

        return lambda e: set_store(update)

    def remove(idx):
        def update(s):
            s.todos.pop(idx)

        return lambda e: set_store(update)

    def summary() -> str:
        todos = list(store.todos)
        done = sum(1 for t in todos if t.done)
        return f"{len(todos)} items, {done} done"

    return div(
        h3("Todo List (draft mutations)"),
        p(dynamic(summary)),
        For(
            each=lambda: list(store.todos),
            key=lambda t: unwrap(t)["id"],
            children=lambda item, idx: div(
                span(
                    dynamic(lambda: f"{'[x]' if item().done else '[ ]'} {item().text}"),
                    on_click=lambda e: toggle(idx())(e),
                    style=lambda: {
                        "cursor": "pointer",
                        "textDecoration": "line-through" if item().done else "none",
                    },
                ),
                button(
                    "x",
                    on_click=lambda e: remove(idx())(e),
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
        def update(s):
            s.settings.theme = "light" if s.settings.theme == "dark" else "dark"

        set_store(update)

    def toggle_notifications(e):
        def update(s):
            s.settings.notifications = not s.settings.notifications

        set_store(update)

    def rename(e):
        def update(s):
            s.user.name = "Grace Hopper" if s.user.name == "Ada Lovelace" else "Ada Lovelace"

        set_store(update)

    return div(
        h3("Nested State (draft mutations)"),
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
            p(
                "Reactive state management for nested objects and lists. "
                "The setter hands you a mutable draft: mutate it with normal "
                "Python and only the changed leaves notify."
            ),
            class_="page-header",
        ),
        h(TodoStore, {}),
        h(NestedStore, {}),
        class_="page",
    )
