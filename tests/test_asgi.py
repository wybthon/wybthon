"""The ASGI app: pages rendered per request, server functions, form posts, handlers, and assets."""

from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

import pytest

from wybthon import server_functions, set_dev_mode
from wybthon.asgi import create_app
from wybthon.build import build_app, init_app
from wybthon.testing import Client

TODOS = '''"""Todos with a flash message for JavaScript-free posts."""

from dataclasses import dataclass

from wybthon import FormData, For, Loading, component, create_memo, html, redirect, server_function
from wybthon.router import RouteProps, form_action, query, use_submissions


@dataclass
class Todo:
    id: int
    title: str


@query
@server_function
async def list_todos() -> list[Todo]:
    from app.server import store

    return [Todo(i, t) for i, t in store.todos()]


@form_action
@server_function
async def add_todo(form: FormData) -> None:
    from app.server import store

    title = str(form.get("title", "")).strip()
    if not title:
        raise ValueError("empty")
    store.add(title)


@form_action
@server_function
async def add_and_leave(form: FormData) -> None:
    from app.server import store

    store.add(str(form["title"]))
    raise redirect("/about")


@query
@server_function
async def guard() -> str:
    raise redirect("/about")
'''

PAGE = '''from wybthon import For, Loading, component, create_memo, html

from app.todos import add_todo, list_todos
from wybthon.router import use_submissions


@component
def Page():
    todos = create_memo(lambda: list_todos())
    submissions = use_submissions(add_todo)

    def row(todo, _index):
        return html(t"<li>{todo.title}</li>")

    def note():
        return "failed" if any(item.error is not None for item in submissions()) else "ok"

    return html(t"""
      <section>
        {Loading(html(t"<ul>{For(todos(), row)}</ul>"), fallback=html(t"<p>Loading...</p>"))}
        <form action={add_todo} method="post"><input name="title"></form>
        <p class="note">{note()}</p>
      </section>
    """)
'''

GUARDED = """from wybthon import component, create_memo, html

from app.todos import guard


@component
def Page():
    value = create_memo(lambda: guard())
    return html(t"<p>{value()}</p>")
"""

API = """import json

from wybthon import component, html, respond
from wybthon.asgi import Response


@component
def Page():
    return html(t"<p>the page</p>")


async def GET(event):
    return {"hello": event.locals["params"].get("name", "world"), "user": event.locals.get("user")}


async def POST(event):
    data = event.request.json()
    return respond({"echo": data}, status=201, headers={"x-made": "yes"})
"""

MIDDLEWARE = """from wybthon.asgi import Response


async def auth(event, call_next):
    if event.request.path == "/blocked":
        return Response("no", 403, {"content-type": "text/plain"})
    event.locals["user"] = event.request.headers.get("x-user", "guest")
    response = await call_next()
    response.headers["x-middleware"] = "1"
    return response
"""


@pytest.fixture
def project(tmp_path: Path):
    """A built full-stack starter with a few extra routes."""
    root = tmp_path / "site"
    init_app(root, server=True)
    (root / "app" / "todos.py").write_text(TODOS)
    (root / "app" / "routes" / "index.py").write_text(PAGE)
    (root / "app" / "routes" / "guarded.py").write_text(GUARDED)
    (root / "app" / "routes" / "api").mkdir()
    (root / "app" / "routes" / "api" / "[name].py").write_text(API)
    (root / "app" / "middleware.py").write_text(MIDDLEWARE)
    config = root / "wybthon.toml"
    config.write_text(
        config.read_text().replace("server = true\n", 'server = true\nmiddleware = ["app.middleware:auth"]\n')
    )
    (root / "public").mkdir()
    (root / "public" / "robots.txt").write_text("User-agent: *\n")
    (root / "public" / ".secret").write_text("hidden")
    build_app(root)
    yield root
    for name in [name for name in sys.modules if name == "app" or name.startswith("app.")]:
        del sys.modules[name]
    for key in [key for key, fn in server_functions._registry.items() if fn.__module__.startswith("app")]:
        del server_functions._registry[key]
    sys.path[:] = [entry for entry in sys.path if entry != str(root)]
    server_functions._base = "/"
    set_dev_mode(True)


def test_a_page_is_rendered_per_request_into_the_shell(project: Path):
    client = Client(create_app(project))
    page = client.get("/")
    assert page.status == 200 and page.headers["content-type"].startswith("text/html")
    assert "<li>Read the Wybthon docs</li>" in page.text
    assert "data-wyb-state" in page.text and '"$dc":"app.todos:Todo"' in page.text
    assert 'id="wyb-manifest"' in page.text and "<!-- wyb:app -->" not in page.text
    assert page.headers["x-middleware"] == "1"
    assert client.request("HEAD", "/").body == b""


def test_an_unknown_url_renders_the_catch_all_with_its_status(project: Path):
    page = Client(create_app(project)).get("/does/not/exist")
    assert page.status == 404 and "Not found" in page.text


def test_a_redirect_from_a_query_becomes_the_response(project: Path):
    page = Client(create_app(project)).get("/guarded")
    assert page.status == 302 and page.headers["location"] == "/about"


def test_a_form_post_without_javascript_redirects_back_with_its_result(project: Path):
    client = Client(create_app(project))
    response = client.post_form("/_wyb/fn/app.todos:add_todo", {"title": "Buy milk"}, referer="/?x=1")
    assert response.status == 303 and response.headers["location"] == "/?x=1"
    assert any(cookie.startswith("wyb_flash=") for cookie in response.cookies)
    page = client.get("/")
    assert "<li>Buy milk</li>" in page.text and '<p class="note">ok</p>' in page.text
    client.post_form("/_wyb/fn/app.todos:add_todo", {"title": " "})
    assert '<p class="note">failed</p>' in client.get("/").text


def test_a_form_post_follows_the_actions_redirect(project: Path):
    client = Client(create_app(project))
    response = client.post_form("/_wyb/fn/app.todos:add_and_leave", {"title": "Go"})
    assert response.status == 303 and response.headers["location"] == "/about"


def test_server_functions_answer_script_calls(project: Path):
    client = Client(create_app(project))
    response = client.request("GET", '/_wyb/fn/app.todos:list_todos?args={"args":[]}', headers={"x-wyb-fn": "1"})
    assert response.status == 200 and response.headers["cache-control"] == "no-store"
    assert response.json()["ok"][0] == {"$dc": "app.todos:Todo", "v": {"id": 1, "title": "Read the Wybthon docs"}}
    forged = client.request(
        "POST",
        "/_wyb/fn/app.todos:add_todo",
        body=b"title=x",
        headers={"content-type": "application/x-www-form-urlencoded", "origin": "https://evil.example"},
    )
    assert forged.status == 403


def test_http_handlers_serve_api_requests_and_pages_still_render(project: Path):
    client = Client(create_app(project))
    data = client.request("GET", "/api/ada", headers={"x-user": "ada"})
    assert data.status == 200 and data.json() == {"hello": "ada", "user": "ada"}
    created = client.request("POST", "/api/ada", body=b'{"a": 1}', headers={"content-type": "application/json"})
    assert created.status == 201 and created.json() == {"echo": {"a": 1}} and created.headers["x-made"] == "yes"
    assert "the page" in client.get("/api/ada").text
    assert client.request("PUT", "/api/ada").status == 405


def test_middleware_can_answer_on_its_own(project: Path):
    blocked = Client(create_app(project)).get("/blocked")
    assert blocked.status == 403 and blocked.text == "no"


def test_assets_are_served_with_their_caching(project: Path):
    client = Client(create_app(project))
    manifest = json.loads((project / "dist" / "manifest.json").read_text())
    asset = client.request("GET", "/" + manifest["runtime"])
    assert asset.status == 200 and "immutable" in asset.headers["cache-control"]
    robots = client.request("GET", "/robots.txt")
    assert (
        robots.status == 200 and robots.headers["cache-control"] == "no-cache" and robots.text.startswith("User-agent")
    )
    assert client.request("GET", "/.secret").status != 200
    assert client.request("GET", "/../wybthon.toml").status != 200


def test_the_browser_archive_has_no_server_code(project: Path):
    manifest = json.loads((project / "dist" / "manifest.json").read_text())
    assert manifest["server"] is True
    with zipfile.ZipFile(project / "dist" / manifest["application"]) as archive:
        names = archive.namelist()
        todos = archive.read("app/todos.py").decode()
        api = archive.read("app/routes/api/[name].py").decode()
    assert not any(name.startswith("app/server/") for name in names)
    assert "store" not in todos and "async def list_todos() -> list[Todo]:\n    ..." in todos
    assert "respond(" not in api.split("def Page")[1]


def test_server_functions_need_a_server_build(tmp_path: Path):
    root = tmp_path / "static"
    init_app(root)
    (root / "app" / "data.py").write_text(
        "from wybthon import server_function\n\n@server_function\nasync def load() -> int:\n    return 1\n"
    )
    with pytest.raises(ValueError, match="server = true"):
        build_app(root)
    (root / "app" / "data.py").unlink()
    build_app(root)
    with pytest.raises(ValueError, match="server build"):
        create_app(root)
