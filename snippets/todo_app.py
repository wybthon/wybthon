"""Todo App — the framework benchmark, in 40 lines of Python.

Tweet caption:
    A full todo app — add, toggle, delete, count — in 40 lines of Python.
    Running in the browser. No JavaScript was harmed in the making.

Why it's interesting:
    `For` keeps per-item reactive scopes, so toggling a single todo
    updates only that row's DOM node. The "X of Y done" line is a memo:
    it recomputes only when `todos` changes.
"""

from wybthon import (
    For,
    button,
    component,
    create_memo,
    create_signal,
    div,
    dynamic,
    input_,
    li,
    p,
    ul,
)


@component
def TodoApp():
    todos, set_todos = create_signal([])
    draft, set_draft = create_signal("")
    done_count = create_memo(lambda: sum(1 for t in todos() if t["done"]))

    def add(_e):
        text = draft().strip()
        if text:
            set_todos([*todos(), {"text": text, "done": False}])
            set_draft("")

    def toggle(i):
        return lambda _e: set_todos([{**t, "done": not t["done"]} if j == i else t for j, t in enumerate(todos())])

    def remove(i):
        return lambda _e: set_todos([t for j, t in enumerate(todos()) if j != i])

    return div(
        p(dynamic(lambda: f"{done_count()} / {len(todos())} done")),
        input_(value=draft, on_input=lambda e: set_draft(e.target.value)),
        button("Add", on_click=add),
        ul(
            For(
                each=todos,
                children=lambda t, i: li(
                    dynamic(lambda: ("[x] " if t()["done"] else "[ ] ") + t()["text"]),
                    button("toggle", on_click=toggle(i())),
                    button("x", on_click=remove(i())),
                ),
            ),
        ),
    )
