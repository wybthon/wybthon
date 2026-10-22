"""E2E: prerendered pages show before Pyodide boots, hydrate without mismatches, and replay early input."""

import contextlib
import socket
import subprocess
import sys
import time
import urllib.request

import pytest

from wybthon.build import build_app, init_app

APP = '''
import asyncio

from wybthon import Loading, NoHydration, component, create_memo, create_signal, html, is_server
from wybthon.router import Link, Route, Router


async def fetch_greeting(name):
    await asyncio.sleep(0.01)
    return f"Hello, {name}"


@component
def Greeting():
    greeting = create_memo(lambda: fetch_greeting("server" if is_server() else "browser"))
    return html(t'<p id="greeting">{greeting()}</p>')


@component
def Home():
    count, set_count = create_signal(0)
    text, set_text = create_signal("")

    def increment():
        set_count(lambda n: n + 1)

    # Kept as the server rendered it: never mounted, so it never updates.
    footer = html(t"""
      <footer id="static">
        <p id="static-count">Static count: {count()}</p>
        <button id="static-button" onclick={(lambda: set_count(100))}>Static</button>
      </footer>
    """)

    return html(t"""
      <div>
        <h1 id="title">Prerendered</h1>
        <button id="count" onclick={increment}>Count: {count()}</button>
        <input id="name" value={text()} oninput={(lambda e: set_text(e.target.value))}>
        <p id="typed">Typed: {text()}</p>
        {Loading(Greeting(), fallback=html(t"<p>Loading greeting</p>"))}
        <{Link} href="/about" id="about-link">About</{Link}>
        {NoHydration(footer)}
      </div>
    """)


@component
def About():
    return html(t'<p id="about">About page</p>')


def app():
    return Router([Route("/", Home), Route("/about", About)])
'''


@pytest.mark.e2e
def test_prerendered_page_hydrates_and_replays_early_input(browser, tmp_path):
    project = tmp_path / "project"
    init_app(project)
    (project / "app" / "main.py").write_text(APP)
    manifest = build_app(project)
    assert manifest["prerendered"] == ["/", "/about"]
    with contextlib.closing(socket.socket()) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    proc = subprocess.Popen(
        [sys.executable, "-m", "wybthon.dev", "preview", "--dir", str(project / "dist"), "--port", str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    page = browser.new_page()
    base = f"http://127.0.0.1:{port}/"
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(base, timeout=1).close()
                break
            except OSError:
                time.sleep(0.05)
        page.goto(base, wait_until="domcontentloaded")
        # The server's HTML is on screen before Python has started.
        assert page.locator("#title").inner_text() == "Prerendered"
        assert page.locator("#static-count").inner_text() == "Static count: 0"
        page.locator("#static").evaluate("node => { node.__serverNode = true; }")
        assert page.locator("#greeting").inner_text() == "Hello, server"
        assert page.evaluate("() => window.__WYB.status") == "loading"
        # Input before hydration is recorded and replayed.
        page.click("#count")
        page.fill("#name", "Ada")
        page.wait_for_function("() => ['ready', 'error'].includes(window.__WYB.status)", timeout=180000)
        assert page.evaluate("() => window.__WYB.error") is None
        assert page.evaluate("() => window.__WYB.hydrated") is True
        assert page.locator("#count").inner_text() == "Count: 1"
        assert page.locator("#typed").inner_text() == "Typed: Ada"
        # The server's data was reused instead of fetched again.
        assert page.locator("#greeting").inner_text() == "Hello, server"
        stats = "from wybthon import kernel; kernel.stats()['hydration_mismatches']"
        mismatches = page.evaluate("(code) => window.__WYB.pyodide.runPython(code)", stats)
        assert mismatches == 0
        page.click("#count")
        assert page.locator("#count").inner_text() == "Count: 2"
        # The NoHydration region keeps the server's nodes and wires nothing.
        assert page.locator("#static").evaluate("node => node.__serverNode === true")
        assert page.locator("#static-count").inner_text() == "Static count: 0"
        page.click("#static-button")
        page.click("#count")
        assert page.locator("#count").inner_text() == "Count: 3"
        assert page.locator("#static-count").inner_text() == "Static count: 0"
        page.click("#about-link")
        page.wait_for_selector("#about")
        page.goto(base + "about", wait_until="domcontentloaded")
        assert page.locator("#about").inner_text() == "About page"
    finally:
        page.close()
        proc.terminate()
        with contextlib.suppress(subprocess.TimeoutExpired):
            proc.wait(timeout=5)
        if proc.poll() is None:
            proc.kill()
