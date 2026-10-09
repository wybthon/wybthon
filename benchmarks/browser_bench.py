#!/usr/bin/env python3
"""Run the browser benchmark app headlessly and report results.

Builds the benchmark app (``benchmarks/app``, an ordinary Wybthon project), serves
it (see ``_app.py``), loads it in headless Chromium via Playwright, clicks "Run Full Benchmark", and
prints separate median synchronous commit and input-to-frame times.
The frame measurement is a rendering opportunity, not a precise paint
completion timestamp. ``bench_runner.py`` measures the native Python backend.

Requires Playwright with Chromium installed:

    pip install playwright
    python -m playwright install chromium

Usage:
    python benchmarks/browser_bench.py            # table output
    python benchmarks/browser_bench.py --json     # JSON output
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from _app import BOOT_TIMEOUT_MS, serve_checkout

REPO_ROOT = Path(__file__).resolve().parents[1]
BENCH_TIMEOUT_MS = 600_000


def run_browser_benchmark(mode: str = "signal") -> dict:
    from playwright.sync_api import sync_playwright

    with serve_checkout(REPO_ROOT) as url, sync_playwright() as p:
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
        page.goto(f"{url}?mode={mode}")

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


def main() -> None:
    parser = argparse.ArgumentParser(description="Wybthon browser benchmark (Pyodide + Playwright)")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    parser.add_argument("--mode", choices=["signal", "store"], default="signal")
    args = parser.parse_args()

    results = run_browser_benchmark(args.mode)

    if args.json:
        print(json.dumps({"benchmarks": results}, indent=2))
    else:
        print()
        print("Wybthon Browser Benchmark (Pyodide, headless Chromium, median of 3)")
        print("=" * 60)
        print(f"{'Benchmark':<24} {'Median (ms)':>12}")
        print("-" * 60)
        for name, result in results["scenarios"].items():
            print(f"{name:<24} {result['sync_commit_ms']:>12.1f}")
        print()


if __name__ == "__main__":
    main()
