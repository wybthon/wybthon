import contextlib
import socket
import subprocess
import time
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def http_server_base_url():
    """Start a simple HTTP server at the repo root for serving demo assets.

    The demo bootstrap fetches from ../../src relative to examples/demo, so we
    must serve the repository root. We select a free port dynamically.
    """
    # Pick an available localhost port
    with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

    repo_root = Path(__file__).resolve().parents[2]
    proc = subprocess.Popen(
        ["python", "-m", "http.server", str(port)],
        cwd=str(repo_root),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    base_url = f"http://127.0.0.1:{port}"

    # Give the server a moment to start
    time.sleep(0.5)

    try:
        yield base_url
    finally:
        with contextlib.suppress(Exception):
            proc.terminate()
        with contextlib.suppress(Exception):
            proc.kill()


@pytest.mark.e2e
def test_demo_bootstraps_pyodide(page, http_server_base_url):
    """Loads the demo page and verifies key UI appears once Pyodide boots.

    This is a light smoke test to validate that the browser + Pyodide path
    initializes and renders the demo component tree.
    """
    page.goto(f"{http_server_base_url}/examples/demo/index.html")

    # Wait for the demo title to render
    page.wait_for_selector("text=Wybthon VDOM Demo", timeout=120_000)

    # Wait for the Hello component to render with its expected text
    page.wait_for_selector("h2.hello:has-text('Hello, Python!')", timeout=120_000)
