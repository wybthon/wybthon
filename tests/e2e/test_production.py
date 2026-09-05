"""Build, deep-link boot, real events, and explicit lazy chunk loading."""

import contextlib
import socket
import subprocess
import sys
import time
import urllib.request

import pytest

from wybthon.build import build_app, init_app


@pytest.mark.e2e
@pytest.mark.parametrize("mode", ["preview", "dev", "retry"])
def test_generated_app_builds_boots_and_loads_chunk(browser, tmp_path, mode):
    project = tmp_path / "project"
    init_app(project)
    (project / "app" / "chart.py").write_text(
        'from wybthon import component, p\n@component\ndef Chart():\n    return p("Chunk loaded", id="chart")\n'
    )
    config = project / "wybthon.toml"
    config.write_text(
        config.read_text()
        .replace('base = "/"', 'base = "/demo/"')
        .replace('# charts = ["app/charts/**"]', 'chart = ["app/chart.py"]')
    )
    main = project / "app" / "main.py"
    main.write_text(
        """from wybthon import Errored, Loading, Show, button, component, create_signal, div, lazy, p, render
Panel = lazy(lambda: ("app.chart", "Chart"), chunk="chart")
@component
def App():
    count, set_count = create_signal(0)
    show, set_show = create_signal(False)
    return div(
        button(lambda: f"Count: {count()}", id="count", on_click=lambda e: set_count(lambda n: n + 1)),
        button("Load chart", id="load", on_click=lambda e: set_show(True)),
        button("Retry", id="retry", on_click=lambda e: Panel.retry()),
        Errored(lambda: Loading(lambda: Show(show, lambda: Panel()), fallback="Loading chart"),
                fallback=lambda error: p("Load failed", id="load-failed")),
    )
def main():
    return render(App(), "#app")
"""
    )
    manifest = build_app(project, base="/demo/")
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
    page = browser.new_page()
    base = f"http://127.0.0.1:{port}/demo/"
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(base, timeout=1).close()
                break
            except OSError:
                time.sleep(0.05)
        requested = []
        page.on("request", lambda request: requested.append(request.url))
        page.goto(base + "a/deep/link")
        page.wait_for_function("() => window.__WYB && ['ready', 'error'].includes(window.__WYB.status)", timeout=180000)
        assert page.evaluate("() => window.__WYB.error") is None
        assert not any(manifest["chunks"]["chart"] in url for url in requested)
        page.click("#count")
        assert page.locator("#count").inner_text() == "Count: 1"
        if mode == "retry":
            page.route("**/" + manifest["chunks"]["chart"], lambda route: route.fulfill(status=503, body="unavailable"))
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
            page.wait_for_function("() => document.querySelector('#count')?.textContent === 'Clicks: 0'", timeout=30000)
    finally:
        page.close()
        proc.terminate()
        with contextlib.suppress(subprocess.TimeoutExpired):
            proc.wait(timeout=5)
        if proc.poll() is None:
            proc.kill()
