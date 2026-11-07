"""E2E: a full-stack app (RFC 0008) served by `wyb serve` and `wyb dev`.

Pages render per request and hydrate; a form action works before Python
has booted (as a plain post) and after (as an action); plain links
navigate without reloading; and the trimmed standard library loads the
rest when an import needs it.
"""

from __future__ import annotations

import contextlib
import socket
import subprocess
import sys
import time
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest

from wybthon.build import init_app

BOOT_TIMEOUT_MS = 180_000

INDEX = '''from wybthon import For, Loading, component, create_memo, html
from wybthon.router import use_submissions

from app.todos import add_todo, list_todos


@component
def Page():
    todos = create_memo(lambda: list_todos())
    submissions = use_submissions(add_todo)

    def row(todo, _index):
        return html(t"<li>{todo.title}</li>")

    def count():
        return str(len(submissions()))

    return html(t"""
      <section>
        <h1 id="title">Todos</h1>
        {Loading(html(t'<ul id="todos">{For(todos(), row)}</ul>'), fallback=html(t"<p>Loading...</p>"))}
        <form id="add" action={add_todo} method="post">
          <input id="new" name="title" required>
          <button id="add-button">Add</button>
        </form>
        <p id="submissions">{count()}</p>
      </section>
    """)
'''


@contextlib.contextmanager
def _server(project: Path, command: list[str]) -> Iterator[str]:
    with contextlib.closing(socket.socket()) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    proc = subprocess.Popen(
        [sys.executable, "-m", "wybthon.dev", *command, "--dir", str(project), "--port", str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base = f"http://127.0.0.1:{port}/"
    try:
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            try:
                urllib.request.urlopen(base, timeout=1).close()
                break
            except OSError:
                time.sleep(0.2)
        yield base
    finally:
        proc.terminate()
        with contextlib.suppress(subprocess.TimeoutExpired):
            proc.wait(timeout=10)


def _ready(page) -> None:
    page.wait_for_function(
        "() => window.__WYB && ['ready', 'error'].includes(window.__WYB.status)", timeout=BOOT_TIMEOUT_MS
    )
    assert page.evaluate("() => window.__WYB.error") is None


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "site"
    init_app(root, server=True)
    (root / "app" / "routes" / "index.py").write_text(INDEX)
    return root


@pytest.mark.e2e
def test_a_production_server_renders_hydrates_and_runs_forms(browser, project: Path):
    with _server(project, ["serve", "--build"]) as base:
        # Without JavaScript, the form posts to the server and comes back.
        static = browser.new_context(java_script_enabled=False)
        try:
            page = static.new_page()
            page.goto(base)
            assert page.locator("#todos li").all_inner_texts() == ["Read the Wybthon docs"]
            page.fill("#new", "Posted without Python")
            page.click("#add-button")
            page.wait_for_url(base)
            assert page.locator("#todos li").all_inner_texts() == ["Read the Wybthon docs", "Posted without Python"]
            assert page.locator("#submissions").inner_text() == "1"
        finally:
            static.close()

        context = browser.new_context()
        try:
            page = context.new_page()
            errors: list[str] = []
            page.on("console", lambda message: errors.append(message.text) if "mismatch" in message.text else None)
            page.goto(base)
            _ready(page)
            assert page.evaluate("() => window.__WYB.hydrated") is True
            assert errors == []
            manifest = page.evaluate("() => JSON.parse(document.getElementById('wyb-manifest').textContent)")
            assert manifest["server"] is True and manifest["stdlib"], "the standard library is trimmed"
            # With Python running, the same form runs as an action, without loading
            # a page, and revalidates the list.
            loads = page.evaluate("() => performance.getEntriesByType('navigation').length")
            page.evaluate("() => { window.__stillHere = true; }")
            page.fill("#new", "Added in the browser")
            page.click("#add-button")
            page.wait_for_function("() => document.querySelectorAll('#todos li').length === 3", timeout=30_000)
            assert page.url == base
            assert page.evaluate("() => window.__stillHere === true")
            assert page.evaluate("() => performance.getEntriesByType('navigation').length") == loads
            # Plain links navigate without loading a page.
            navigations = page.evaluate("() => performance.getEntriesByType('navigation').length")
            page.click("a[href='/about']")
            page.wait_for_selector("h1:has-text('About')")
            assert page.evaluate("() => performance.getEntriesByType('navigation').length") == navigations
            page.go_back()
            page.wait_for_selector("#title")
            # A module the build trimmed loads on demand.
            assert (
                page.evaluate("() => window.__WYB.pyodide.runPython('import email.utils\\nemail.utils.quote(\"a\")')")
                == "a"
            )
            # An unknown URL is the catch-all's 404.
            response = page.request.get(base + "missing")
            assert response.status == 404
        finally:
            context.close()


@pytest.mark.e2e
def test_the_dev_server_renders_per_request_and_updates(browser, project: Path):
    with _server(project, ["dev"]) as base:
        page = browser.new_page()
        try:
            page.goto(base)
            _ready(page)
            assert page.locator("#todos li").all_inner_texts() == ["Read the Wybthon docs"]
            # A server-side change is picked up by the next request.
            store = project / "app" / "server" / "store.py"
            store.write_text(store.read_text().replace("Read the Wybthon docs", "Edited on the server"))
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                with urllib.request.urlopen(base, timeout=5) as response:
                    if "Edited on the server" in response.read().decode():
                        break
                time.sleep(0.5)
            else:
                pytest.fail("the dev server didn't pick up the change")
        finally:
            page.close()
