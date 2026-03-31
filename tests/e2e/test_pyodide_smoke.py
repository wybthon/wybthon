import contextlib
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def http_server_base_url():
    """Start the Wybthon dev server at the repo root for serving demo assets.

    Uses ``wyb dev`` so the ``/__manifest`` endpoint is available for
    bootstrap.js to dynamically discover Python files.
    """
    # Pick an available localhost port
    with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

    repo_root = Path(__file__).resolve().parents[2]
    proc = subprocess.Popen(
        [sys.executable, "-m", "wybthon.dev", "dev", "--port", str(port), "--dir", str(repo_root)],
        cwd=str(repo_root),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    base_url = f"http://127.0.0.1:{port}"

    # Give the server a moment to start
    time.sleep(1)

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

    # Wait for the header brand to render (confirms Pyodide booted and app mounted)
    page.wait_for_selector(".header-brand h1", timeout=120_000)

    # Verify the home page hero section rendered
    page.wait_for_selector("h2.hero-title", timeout=120_000)

    # Navigate to the About page (lazy-loaded) and verify content appears
    page.click("a.nav-link:has-text('About')")
    page.wait_for_selector("text=About Wybthon", timeout=120_000)
