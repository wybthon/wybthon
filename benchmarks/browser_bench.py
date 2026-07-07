#!/usr/bin/env python3
"""Run the browser benchmark app headlessly and report results.

Serves the repository root over HTTP, loads ``benchmarks/app/index.html``
in headless Chromium via Playwright, clicks "Run Full Benchmark", and
prints the median results the page reports. This measures the real
end-to-end cost (Pyodide FFI + browser layout), unlike the stubbed
``bench_runner.py`` which isolates Python-side framework cost.

Requires Playwright with Chromium installed:

    pip install playwright
    python -m playwright install chromium

Usage:
    python benchmarks/browser_bench.py            # table output
    python benchmarks/browser_bench.py --json     # JSON output
"""

from __future__ import annotations

import argparse
import contextlib
import json
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_URL_PATH = "/benchmarks/app/index.html"

# Pyodide boots from a CDN; allow a generous ceiling for cold starts / CI.
BOOT_TIMEOUT_MS = 300_000
BENCH_TIMEOUT_MS = 600_000


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
    raise RuntimeError(f"HTTP server did not become ready at {url}: {last_err}")


def run_browser_benchmark() -> dict:
    from playwright.sync_api import sync_playwright

    port = _free_port()
    server = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
        cwd=str(REPO_ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base_url = f"http://127.0.0.1:{port}"
    try:
        _wait_for_http(f"{base_url}{APP_URL_PATH}")
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()

            results_json: list[str] = []

            def on_console(msg):
                text = msg.text
                if "RESULTS_JSON=" in text:
                    results_json.append(text.split("RESULTS_JSON=", 1)[1])
                elif text.startswith("[BENCH]"):
                    print(text, file=sys.stderr)

            page.on("console", on_console)
            page.goto(f"{base_url}{APP_URL_PATH}")

            # The benchmark panel appears once Pyodide and the app have loaded.
            page.wait_for_selector("#bench-panel", state="visible", timeout=BOOT_TIMEOUT_MS)
            page.click("#run-bench-btn")
            page.wait_for_function(
                "() => document.getElementById('run-bench-btn').textContent.includes('Complete')",
                timeout=BENCH_TIMEOUT_MS,
            )
            browser.close()

        if not results_json:
            raise RuntimeError("Benchmark finished but no RESULTS_JSON line was captured")
        return json.loads(results_json[-1])
    finally:
        with contextlib.suppress(Exception):
            server.terminate()
        with contextlib.suppress(Exception):
            server.wait(timeout=5)
        with contextlib.suppress(Exception):
            server.kill()


def main() -> None:
    parser = argparse.ArgumentParser(description="Wybthon browser benchmark (Pyodide + Playwright)")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    args = parser.parse_args()

    results = run_browser_benchmark()

    if args.json:
        print(json.dumps({"benchmarks": results}, indent=2))
    else:
        print()
        print("Wybthon Browser Benchmark (Pyodide, headless Chromium, median of 3)")
        print("=" * 60)
        print(f"{'Benchmark':<24} {'Median (ms)':>12}")
        print("-" * 60)
        for name, ms in results.items():
            print(f"{name:<24} {ms:>12.1f}")
        print()


if __name__ == "__main__":
    main()
