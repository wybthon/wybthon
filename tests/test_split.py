"""What the browser's copy of a module leaves out (`wybthon._split`)."""

from wybthon._split import client_source, split

SOURCE = '''"""Todos."""
from __future__ import annotations

import json, os
from dataclasses import dataclass
from app.server.db import database, helper as h
import wybthon
from wybthon import server_function as sf, html


@dataclass
class Todo:
    id: int


@sf
async def save(todo: "Todo") -> None:
    """Saves."""
    database().execute("insert into todos values (?)", [todo.id])  # secret
    h(os.environ["KEY"])


@wybthon.server_function(method="GET")
async def count() -> int: return len(database())


def view():
    return html(t"<p>{json.dumps(1)}</p>")
'''


def test_server_function_bodies_and_their_imports_are_removed():
    result = split(SOURCE)
    assert result.functions == ("save", "count")
    browser = result.source
    assert "secret" not in browser and "database" not in browser and "os.environ" not in browser
    assert "import json\n" in browser and "from dataclasses import dataclass" in browser
    assert 'async def save(todo: "Todo") -> None:\n    ...' in browser
    assert "async def count() -> int: ..." in browser
    compile(browser, "todos.py", "exec")


def test_lines_stay_where_they_were():
    browser = client_source(SOURCE)
    assert browser.count("\n") == SOURCE.count("\n")
    original = SOURCE.splitlines()
    for index, line in enumerate(browser.splitlines()):
        if line.startswith("def view"):
            assert original[index] == line


def test_names_used_outside_server_functions_stay_imported():
    source = (
        "from wybthon import server_function\nfrom app.db import Row, query\n\n"
        "@server_function\nasync def rows() -> list[Row]:\n    return query()\n"
    )
    browser = client_source(source)
    assert "from app.db import Row\n" in browser and "query" not in browser.split("async def")[0]


def test_file_route_handlers_are_server_only():
    source = (
        "from wybthon import html\nimport secrets\n\n"
        "async def GET(event):\n    return secrets.token_hex()\n\n"
        'def Page():\n    return html(t"<p>hi</p>")\n'
    )
    assert "secrets" in client_source(source)
    result = split(source, handlers=True)
    assert result.handlers == ("GET",) and "secrets" not in result.source


def test_modules_without_server_code_are_returned_as_is():
    source = "import os\nx = os.sep\n"
    assert client_source(source) is source or client_source(source) == source
