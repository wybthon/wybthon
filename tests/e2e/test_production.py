"""Build, deep-link boot, real events, dev mode, compiled templates, and explicit lazy chunk loading."""

import contextlib
import json
import socket
import subprocess
import sys
import time
import urllib.request

import pytest

from wybthon.build import build_app, init_app

BOOT_TIMEOUT_MS = 180_000


@contextlib.contextmanager
def _serve(project, mode, base_path="/"):
    """Serve `project` with `wyb dev` (mode "dev") or its built `dist/` with `wyb preview`."""
    with contextlib.closing(socket.socket()) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "wybthon.dev",
            "dev" if mode == "dev" else "preview",
            "--dir",
            str(project if mode == "dev" else project / "dist"),
            "--port",
            str(port),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base = f"http://127.0.0.1:{port}{base_path}"
    try:
        # `wyb dev` builds (and prerenders) before it serves; give a loaded
        # machine time instead of a fixed number of quick retries.
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            try:
                urllib.request.urlopen(base, timeout=1).close()
                break
            except OSError:
                time.sleep(0.1)
        yield base
    finally:
        proc.terminate()
        with contextlib.suppress(subprocess.TimeoutExpired):
            proc.wait(timeout=5)
        if proc.poll() is None:
            proc.kill()


def _wait_ready(page):
    page.wait_for_function(
        "() => window.__WYB && ['ready', 'error'].includes(window.__WYB.status)", timeout=BOOT_TIMEOUT_MS
    )
    assert page.evaluate("() => window.__WYB.error") is None


DEV_MODE_APP = '''
import wybthon
from wybthon import For, Props, Show, component, create_signal, html


class LabelProps(Props):
    text: str


@component
def Label(props: LabelProps):
    return html(t'<p id="label">{props.text}</p>')


def checked():
    # Dev mode validates component props at the call site; production skips it.
    try:
        Label(text="x", bogus=1)
    except TypeError:
        return "checked"
    return "unchecked"


def row(item, index):
    return html(t"<li>{index()}:{item.upper()}</li>")


@component
def App():
    items, set_items = create_signal(["a", "b"])

    def add():
        set_items(lambda xs: [*xs, "c"])

    return html(t"""
      <div>
        <{Label} text="Mode" />
        <p id="mode">{"dev" if wybthon.is_dev_mode() else "production"}</p>
        <p id="props-check">{checked()}</p>
        <p id="size">{len(items()) * 10}</p>
        <ul id="rows">{For(items(), row)}</ul>
        {Show(len(items()) > 2, html(t'<p id="many">many</p>'))}
        <button id="add" onclick={add}>add</button>
      </div>
    """)


def app():
    return App()
'''

# Evaluated in the page once the app has rendered and updated: the
# compiled bundle never parses a template (the run-time caches stay
# empty), and every literal the app rendered came precompiled.
PRECOMPILED_CHECK = """
import json, sys
from wybthon import templates

entries = [
    value
    for name, module in list(sys.modules.items())
    if name == "app" or name.startswith("app.")
    for key, value in vars(module).items()
    if key.startswith("__wybthon_t") and isinstance(value, templates.Precompiled)
]
json.dumps({
    "by_identity": len(templates._by_identity),
    "by_value": len(templates._by_value),
    "entries": len(entries),
    "loaded": sum(entry.entry is not None for entry in entries),
})
"""


@pytest.mark.e2e
@pytest.mark.parametrize("mode", ["preview", "dev"])
def test_build_turns_dev_mode_off_and_dev_keeps_it_on(browser, tmp_path, mode):
    project = tmp_path / "project"
    init_app(project)
    (project / "app" / "main.py").write_text(DEV_MODE_APP)
    manifest = build_app(project)
    # `wyb build` (and `build_app`'s default) produces a production bundle.
    assert manifest["dev"] is False
    page = browser.new_page()
    try:
        with _serve(project, mode) as base:
            page.goto(base)
            _wait_ready(page)
            dev = mode == "dev"
            assert page.evaluate("() => window.__WYB.pyodide.runPython('import wybthon; wybthon.is_dev_mode()')") is dev
            assert page.locator("#mode").inner_text() == ("dev" if dev else "production")
            assert page.locator("#props-check").inner_text() == ("checked" if dev else "unchecked")
            assert page.locator("#label").inner_text() == "Mode"
            # Compiled expressions are reactive in either mode.
            assert page.locator("#size").inner_text() == "20"
            assert page.locator("#rows li").all_inner_texts() == ["0:A", "1:B"]
            assert page.locator("#many").count() == 0
            page.click("#add")
            page.wait_for_selector("#many")
            assert page.locator("#size").inner_text() == "30"
            assert page.locator("#rows li").all_inner_texts() == ["0:A", "1:B", "2:C"]
            check = "(code) => window.__WYB.pyodide.runPython(code)"
            result = json.loads(page.evaluate(check, PRECOMPILED_CHECK))
            assert result["by_identity"] == 0, result
            assert result["by_value"] == 0, result
            # Label, the row, the `many` paragraph, and App.
            assert result["entries"] == 4, result
            assert result["loaded"] == 4, result
    finally:
        page.close()


CHART = """from wybthon import component, html


@component
def Chart():
    return html(t'<p id="chart">Chunk loaded</p>')
"""

CHUNK_APP = '''from wybthon import Errored, Loading, Show, component, create_signal, html, lazy

Panel = lazy(lambda: ("app.chart", "Chart"), chunk="chart")


@component
def App():
    count, set_count = create_signal(0)
    show, set_show = create_signal(False)

    def failed(err):
        return html(t'<p id="load-failed" title={str(err())}>Load failed</p>')

    return html(t"""
      <div>
        <button id="count" onclick={(lambda: set_count(lambda n: n + 1))}>Count: {count()}</button>
        <button id="load" onclick={(lambda: set_show(True))}>Load chart</button>
        <button id="retry" onclick={(lambda: Panel.retry())}>Retry</button>
        {Errored(Loading(Show(show(), (lambda: Panel())), fallback="Loading chart"), fallback=failed)}
      </div>
    """)


def app():
    return App()
'''


@pytest.mark.e2e
@pytest.mark.parametrize("mode", ["preview", "dev", "retry"])
def test_generated_app_builds_boots_and_loads_chunk(browser, tmp_path, mode):
    project = tmp_path / "project"
    init_app(project)
    (project / "app" / "chart.py").write_text(CHART)
    config = project / "wybthon.toml"
    config.write_text(
        config.read_text()
        .replace('base = "/"', 'base = "/demo/"')
        .replace('# charts = ["app/charts/**"]', 'chart = ["app/chart.py"]')
    )
    main = project / "app" / "main.py"
    main.write_text(CHUNK_APP)
    manifest = build_app(project, base="/demo/")
    page = browser.new_page()
    try:
        with _serve(project, mode, "/demo/") as base:
            requested = []
            page.on("request", lambda request: requested.append(request.url))
            page.goto(base + "a/deep/link")
            _wait_ready(page)
            assert not any(manifest["chunks"]["chart"] in url for url in requested)
            page.click("#count")
            assert page.locator("#count").inner_text() == "Count: 1"
            if mode == "retry":
                page.route(
                    "**/" + manifest["chunks"]["chart"], lambda route: route.fulfill(status=503, body="unavailable")
                )
            page.click("#load")
            if mode == "retry":
                page.wait_for_selector("#load-failed")
                page.unroute("**/" + manifest["chunks"]["chart"])
                page.click("#retry")
            page.wait_for_selector("#chart")
            assert page.locator("#chart").inner_text() == "Chunk loaded"
            assert sum(manifest["chunks"]["chart"] in url for url in requested) == (2 if mode == "retry" else 1)
            assert page.evaluate("() => window.__WYB.timings.ready_ms") > 0
            if mode == "dev":
                main.write_text(main.read_text().replace("Count:", "Clicks:"))
                page.wait_for_function(
                    "() => document.querySelector('#count')?.textContent === 'Clicks: 0'", timeout=30000
                )
    finally:
        page.close()


@pytest.mark.e2e
@pytest.mark.parametrize("mode", ["preview", "dev"])
def test_later_boots_restore_a_snapshot_of_the_framework(browser, tmp_path, mode):
    project = tmp_path / "project"
    init_app(project)
    (project / "app" / "chart.py").write_text(CHART)
    config = project / "wybthon.toml"
    config.write_text(config.read_text().replace('# charts = ["app/charts/**"]', 'chart = ["app/chart.py"]'))
    (project / "app" / "main.py").write_text(CHUNK_APP)
    build_app(project)
    context = browser.new_context()
    try:
        with _serve(project, mode) as base:
            first = context.new_page()
            first.goto(base)
            _wait_ready(first)
            assert first.evaluate("() => window.__WYB.timings.snapshot") is False
            # The first boot builds a snapshot in a worker once the page is idle.
            first.wait_for_function("() => window.__WYB.snapshot !== undefined", timeout=BOOT_TIMEOUT_MS)
            assert first.evaluate("() => window.__WYB.snapshot.built") is True, first.evaluate(
                "() => window.__WYB.snapshot"
            )
            first.close()
            page = context.new_page()
            page.goto(base)
            _wait_ready(page)
            assert page.evaluate("() => window.__WYB.timings.snapshot") is True
            assert page.evaluate("() => window.__WYB.pyodide.runPython('import wybthon; wybthon.is_dev_mode()')") is (
                mode == "dev"
            )
            # The restored runtime runs the application, and its file system
            # still serves imports and lazy chunks.
            page.click("#count")
            assert page.locator("#count").inner_text() == "Count: 1"
            page.click("#load")
            page.wait_for_selector("#chart")
            # A restored page doesn't build another snapshot.
            page.wait_for_timeout(500)
            assert page.evaluate("() => window.__WYB.snapshot") is None
    finally:
        context.close()


HOT_STATE = """from wybthon import create_signal

clicks, set_clicks = create_signal(0)
"""

HOT_APP = """from wybthon import component, html

from app.state import clicks, set_clicks


@component
def App():
    def bump():
        set_clicks(lambda n: n + 1)

    return html(t'<div><button id="bump" onclick={bump}>Clicks: {clicks()}</button></div>')


def app():
    return App()
"""


@pytest.mark.e2e
def test_dev_replaces_an_edited_module_without_reloading(browser, tmp_path):
    project = tmp_path / "project"
    init_app(project)
    (project / "app" / "state.py").write_text(HOT_STATE)
    main = project / "app" / "main.py"
    main.write_text(HOT_APP)
    page = browser.new_page()
    try:
        with _serve(project, "dev") as base:
            page.goto(base)
            _wait_ready(page)
            page.click("#bump")
            page.click("#bump")
            assert page.locator("#bump").inner_text() == "Clicks: 2"
            # A marker a reload would erase.
            page.evaluate("() => { window.__kept = true; }")
            main.write_text(main.read_text().replace("Clicks:", "Presses:"))
            page.wait_for_function("() => document.querySelector('#bump')?.textContent === 'Presses: 2'", timeout=30000)
            assert page.evaluate("() => window.__kept === true && window.__WYB.hot === 1")
            page.click("#bump")
            assert page.locator("#bump").inner_text() == "Presses: 3"
            # Markup outside the application's modules still reloads the page.
            index = project / "index.html"
            index.write_text(index.read_text().replace("<title>Wybthon app</title>", "<title>Changed</title>"))
            page.wait_for_function("() => document.title === 'Changed'", timeout=30000)
            _wait_ready(page)
            assert page.evaluate("() => window.__kept") is None
    finally:
        page.close()
