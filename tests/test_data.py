"""The router's data layer: `query`, `revalidate`, `form_action`, and submissions."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from wybthon import (
    For,
    FormData,
    Loading,
    RequestEvent,
    ServerError,
    component,
    create_memo,
    create_optimistic,
    flush,
    html,
    server_function,
)
from wybthon.router import (
    Route,
    _data,
    create_router,
    form_action,
    navigate,
    query,
    revalidate,
    url,
    use_submissions,
)
from wybthon.testing import connect_server, fire, render, tick


@dataclass
class Todo:
    id: int
    title: str


_todos: list[Todo] = []
_reads: list[str] = []


@query
@server_function
async def list_todos() -> list[Todo]:
    _reads.append("todos")
    return list(_todos)


@query("user")
async def get_user(user_id: int) -> str:
    _reads.append(f"user {user_id}")
    await asyncio.sleep(0)
    return f"user {user_id}"


@form_action
@server_function
async def add_todo(form: FormData) -> Todo:
    title = str(form["title"]).strip()
    if not title:
        raise ServerError("A todo needs a title", "ValueError")
    todo = Todo(len(_todos) + 1, title)
    _todos.append(todo)
    return todo


@form_action
@server_function
async def rename(todo_id: int, form: FormData) -> None:
    for todo in _todos:
        if todo.id == todo_id:
            todo.title = str(form["title"])


@form_action
@server_function
async def leave(form: FormData) -> None:
    from wybthon import redirect

    raise redirect("/done")


def find(node, tag):
    if getattr(node, "tag", None) == tag:
        return node
    for child in getattr(node, "childNodes", []):
        found = find(child, tag)
        if found is not None:
            return found
    return None


def reset() -> None:
    _todos[:] = [Todo(1, "first")]
    _reads.clear()
    _data._entries.clear()
    navigate("/")
    flush()


@component
def TodoList():
    todos = create_memo(lambda: list_todos())
    submissions = use_submissions(add_todo)

    def row(todo, _index):
        return html(t"<li>{todo.title}</li>")

    def errors():
        return ", ".join(str(item.error) for item in submissions() if item.error is not None)

    return html(t"""
      <div>
        {Loading(html(t"<ul>{For(todos(), row)}</ul>"), fallback="loading")}
        <form action={add_todo} method="post"><input name="title"><button>Add</button></form>
        <p>{errors()}</p>
      </div>
    """)


def test_a_query_key_defaults_to_the_server_function_and_switches_it_to_get():
    assert list_todos.key == list_todos.__wrapped__.id
    assert list_todos.__wrapped__.method == "GET"
    assert get_user.key == "user" and get_user.key_for(3) == "user[3]"
    assert query(lambda: None, "k").key == "k"


def test_queries_dedupe_in_the_browser_and_refetch_on_revalidate():
    reset()

    async def main() -> None:
        @component
        def Users():
            a = create_memo(lambda: get_user(1))
            b = create_memo(lambda: get_user(1))
            return html(t"<p>{a()}|{b()}</p>")

        with render(Loading(Users(), fallback="wait")) as screen:
            await tick(4)
            assert screen.text() == "user 1|user 1"
            assert _reads == ["user 1"]
            revalidate("us")
            await tick(4)
            assert _reads == ["user 1", "user 1"]
            revalidate("other")
            await tick(4)
            assert _reads == ["user 1", "user 1"]
            revalidate(get_user)
            await tick(4)
            assert len(_reads) == 3 and screen.text() == "user 1|user 1"

    asyncio.run(main())


def test_queries_dedupe_per_request_on_the_server():
    reset()

    async def main() -> None:
        from wybthon.request import _current

        token = _current.set(RequestEvent())
        try:
            first, second = await asyncio.gather(get_user(2), get_user(2))
        finally:
            _current.reset(token)
        assert first == second == "user 2" and _reads == ["user 2"]

    asyncio.run(main())


def test_a_form_posts_to_its_action_and_the_page_revalidates():
    reset()

    async def main() -> None:
        with connect_server(), render(TodoList()) as screen:
            await tick(4)
            assert [item.text_content for item in screen.get_all_by_role("listitem")] == ["first"]
            form = find(screen.container, "form")
            assert form.getAttribute("action") == "/_wyb/fn/" + add_todo.name
            fire.input(screen.get_by_role("textbox"), "second")
            fire.submit(form)
            assert form.getAttribute("aria-busy") == "true"
            assert add_todo.pending() is True
            await tick(8)
            assert [item.text_content for item in screen.get_all_by_role("listitem")] == ["first", "second"]
            assert form.getAttribute("aria-busy") is None
            assert _reads == ["todos", "todos"]
            fire.input(screen.get_by_role("textbox"), " ")
            fire.submit(form)
            await tick(8)
            assert screen.text().endswith("A todo needs a title")

    asyncio.run(main())


def test_bound_arguments_ride_in_the_url():
    reset()

    @component
    def Rename():
        return html(t'<form action={rename.bind(1)} method="post"><input name="title"></form>')

    async def main() -> None:
        with connect_server(), render(Rename()) as screen:
            form = find(screen.container, "form")
            assert "?args=" in form.getAttribute("action")
            fire.input(screen.get_by_role("textbox"), "renamed")
            fire.submit(form)
            await tick(8)
        assert _todos[0].title == "renamed"
        history = use_submissions(rename)()
        assert history[-1].input[0] == 1 and isinstance(history[-1].input[1], FormData)

    asyncio.run(main())


def test_submission_hooks_and_history():
    reset()
    seen: list[str] = []

    async def shout(form: FormData) -> str:
        await asyncio.sleep(0)
        return str(form["title"]).upper()

    local = form_action(shout, "local")

    async def main() -> None:
        assert form_action(local) is local
        optimistic, set_optimistic = create_optimistic(0)

        @component
        def Page():
            local.on_submit(lambda form: set_optimistic(lambda n: n + 1))
            local.on_settled(lambda submission: seen.append(submission.result))
            return html(t'<form action={local} method="post"><input name="title"><b>{optimistic()}</b></form>')

        with render(Page()) as screen:
            fire.input(screen.get_by_role("textbox"), "hey")
            fire.submit(find(screen.container, "form"))
            assert screen.get_by_text("1")
            await tick(8)
            assert seen == ["HEY"]
            assert screen.get_by_text("0")
            history = use_submissions(local)()
            assert [item.result for item in history] == ["HEY"]
            history[0].clear()
            flush()
            assert use_submissions(local)() == []

    asyncio.run(main())


def test_a_client_action_needs_a_name():
    import pytest

    async def unnamed(form: FormData) -> None: ...

    with pytest.raises(TypeError, match="name"):
        form_action(unnamed)


def test_a_redirecting_action_navigates():
    reset()

    @component
    def Leave():
        return html(t'<form action={leave} method="post"></form>')

    router = create_router([Route("/", Leave)])

    async def main() -> None:
        with connect_server(), render(router()) as screen:
            fire.submit(find(screen.container, "form"))
            await tick(8)
            assert url.peek() == "/done"

    asyncio.run(main())
    navigate("/")
    flush()
