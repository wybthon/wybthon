"""Shared fixtures for the Wybthon browser E2E suite.

Design goals:

- **Boot Pyodide once.** Pyodide cold-start dominates runtime, so a single
  session-scoped page boots the fixture SPA and every test navigates within
  it using the History-API router (no full reloads).
- **Deterministic isolation.** ``goto_feature`` bounces through ``/blank``
  before navigating to the target feature, forcing the previous feature's
  component tree to unmount so each test starts from fresh component state.
- **Fail fast on boot errors.** ``bootstrap.js`` records a boot error on
  ``window.__WYB_E2E_ERROR``; the readiness wait surfaces it as a test error
  instead of timing out.
"""

from __future__ import annotations

import contextlib
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_URL_PATH = "/tests/e2e/index.html"

# Pyodide boots from a CDN; allow a generous ceiling for cold starts / CI.
BOOT_TIMEOUT_MS = 180_000
NAV_TIMEOUT_MS = 30_000


def _free_port() -> int:
    with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_for_http(url: str, timeout_s: float = 30.0) -> None:
    deadline = time.time() + timeout_s
    last_err: Exception | None = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if resp.status == 200:
                    return
        except (urllib.error.URLError, ConnectionError, OSError) as exc:
            last_err = exc
        time.sleep(0.25)
    raise RuntimeError(f"Dev server did not become ready at {url}: {last_err}")


@pytest.fixture(scope="session")
def http_server_base_url():
    """Start ``wyb dev`` at the repo root so the fixture app and manifest load."""
    port = _free_port()
    proc = subprocess.Popen(
        [sys.executable, "-m", "wybthon.dev", "dev", "--port", str(port), "--dir", str(REPO_ROOT)],
        cwd=str(REPO_ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base_url = f"http://127.0.0.1:{port}"
    try:
        _wait_for_http(f"{base_url}{FIXTURE_URL_PATH}")
        yield base_url
    finally:
        with contextlib.suppress(Exception):
            proc.terminate()
        with contextlib.suppress(Exception):
            proc.wait(timeout=5)
        with contextlib.suppress(Exception):
            proc.kill()


@pytest.fixture(scope="session")
def fixture_page(http_server_base_url, browser):
    """A single page with the fixture SPA booted once for the whole session."""
    page = browser.new_page()
    page.set_default_timeout(NAV_TIMEOUT_MS)
    page.goto(f"{http_server_base_url}{FIXTURE_URL_PATH}")

    page.wait_for_function(
        "() => window.__WYB_E2E_READY === true || window.__WYB_E2E_ERROR",
        timeout=BOOT_TIMEOUT_MS,
    )
    boot_error = page.evaluate("() => window.__WYB_E2E_ERROR")
    if boot_error:
        raise RuntimeError(f"Wybthon fixture failed to boot:\n{boot_error}")
    page.wait_for_selector("[data-testid=app-ready]", timeout=BOOT_TIMEOUT_MS)

    yield page
    with contextlib.suppress(Exception):
        page.close()


@pytest.fixture
def goto_feature(fixture_page):
    """Return a helper that navigates to a top-level feature with a fresh mount."""

    def _go(slug: str):
        fixture_page.click("[data-testid=nav-blank]")
        fixture_page.wait_for_selector("[data-testid=page-blank]")
        fixture_page.click(f"[data-testid=nav-{slug}]")
        fixture_page.wait_for_selector(f"[data-testid=page-{slug}]")
        return fixture_page

    return _go


@pytest.fixture
def goto_path(fixture_page):
    """Return a helper that navigates to an arbitrary base-relative path."""

    def _go(path: str, wait_selector: str | None = None):
        fixture_page.click("[data-testid=nav-blank]")
        fixture_page.wait_for_selector("[data-testid=page-blank]")
        fixture_page.evaluate("(p) => window.__wyb_e2e_goto(p)", path)
        if wait_selector:
            fixture_page.wait_for_selector(wait_selector)
        return fixture_page

    return _go
