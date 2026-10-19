"""Serve a checkout's browser benchmark app for Playwright.

A checkout whose `benchmarks/app` is a Wybthon project (it has a
`wybthon.toml`) is built with that checkout's own `wyb build` and its `dist`
is served at the site root. Older checkouts, whose benchmark page loaded the
framework's sources itself, are served with their own `benchmarks/_serve.py`,
so any two checkouts can still be compared.
"""

from __future__ import annotations

import contextlib
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path

# Pyodide boots from a CDN; allow a generous ceiling for cold starts and CI.
BOOT_TIMEOUT_MS = 300_000


def free_port() -> int:
    with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_for_http(url: str, timeout_s: float = 30.0) -> None:
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
    raise RuntimeError(f"HTTP server did not become ready at {url}: {last_err}")


def _build(repo: Path, output: Path) -> None:
    env = {**os.environ, "PYTHONPATH": str(repo / "src")}
    code = (
        "import sys; from pathlib import Path; from wybthon.build import build_app; "
        "build_app(Path(sys.argv[1]), output=Path(sys.argv[2]))"
    )
    subprocess.run(
        [sys.executable, "-c", code, str(repo / "benchmarks" / "app"), str(output)], env=env, check=True, cwd=repo
    )


@contextlib.contextmanager
def serve_checkout(repo: Path) -> Iterator[str]:
    """Serve `repo`'s benchmark app; yields the page URL."""
    repo = repo.resolve()
    port = free_port()
    with tempfile.TemporaryDirectory(prefix="wyb-bench-") as temporary:
        if (repo / "benchmarks" / "app" / "wybthon.toml").exists():
            dist = Path(temporary) / "dist"
            _build(repo, dist)
            command = [sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1", "--directory", str(dist)]
            url = f"http://127.0.0.1:{port}/"
        else:
            serve = repo / "benchmarks" / "_serve.py"
            command = [sys.executable, str(serve), "--port", str(port), "--root", str(repo)]
            url = f"http://127.0.0.1:{port}/benchmarks/app/index.html"
        server = subprocess.Popen(command, cwd=repo, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            wait_for_http(url)
            yield url
        finally:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)
