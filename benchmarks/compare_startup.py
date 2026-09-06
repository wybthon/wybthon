"""Compare fresh production app boots with a warmed browser HTTP cache.

Build the same starter app from two source checkouts. Alternate navigation
order, starting a fresh Pyodide runtime on every navigation. Warmup boots
populate the shared HTTP cache and are excluded from the measurements.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path

from browser_bench import BOOT_TIMEOUT_MS, REPO_ROOT, _free_port, _wait_for_http
from playwright.sync_api import sync_playwright


@contextlib.contextmanager
def production(repo, project):
    env = dict(os.environ, PYTHONPATH=str(repo / "src"))
    subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from pathlib import Path; from wybthon.build import init_app, build_app; "
            "p = Path(sys.argv[1]); init_app(p); build_app(p)",
            str(project),
        ],
        cwd=repo,
        env=env,
        check=True,
    )
    port = _free_port()
    server = subprocess.Popen(
        [sys.executable, "-m", "wybthon.dev", "preview", "--dir", str(project / "dist"), "--port", str(port)],
        cwd=repo,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}/"
    try:
        _wait_for_http(url)
        yield url
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=5)


def compare(baseline, iterations, warmup):
    with contextlib.ExitStack() as stack:
        temporary = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix="wyb-startup-")))
        urls = {
            side: stack.enter_context(production(repo, temporary / side))
            for side, repo in (("before", baseline), ("after", REPO_ROOT))
        }
        playwright = stack.enter_context(sync_playwright())
        browser = playwright.chromium.launch()
        stack.callback(browser.close)
        context = browser.new_context()
        pages = {side: context.new_page() for side in urls}
        samples = {side: [] for side in urls}
        for iteration in range(warmup + iterations):
            for side in (("before", "after") if iteration % 2 == 0 else ("after", "before")):
                page = pages[side]
                page.bring_to_front()
                page.goto(urls[side])
                page.wait_for_function(
                    "() => window.__WYB && ['ready', 'error'].includes(window.__WYB.status)", timeout=BOOT_TIMEOUT_MS
                )
                assert page.evaluate("() => window.__WYB.error") is None
                result = page.evaluate("async () => { await window.__WYB.ready; return {...window.__WYB.timings}; }")
                assert page.locator("button").inner_text() == "Count: 0"
                page.click("button")
                assert page.locator("button").inner_text() == "Count: 1"
                if iteration >= warmup:
                    samples[side].append(result)
            print(f"Startup pair {iteration + 1}/{warmup + iterations} complete", file=sys.stderr, flush=True)
        summaries = {
            side: {key: statistics.median(sample[key] for sample in values) for key in values[0]}
            for side, values in samples.items()
        }
        return {
            "metadata": {
                "browser": browser.version,
                "method": "alternating fresh production boots with warmed shared HTTP cache",
                "iterations": iterations,
                "warmup": warmup,
                "manifests": {
                    side: json.loads((temporary / side / "dist" / "manifest.json").read_text()) for side in urls
                },
            },
            "medians": summaries,
            "samples": samples,
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--iterations", type=int, default=5)
    parser.add_argument("--warmup", type=int, default=1)
    args = parser.parse_args()
    if args.iterations < 1 or args.warmup < 1:
        parser.error("iterations and warmup must both be positive")
    print(json.dumps(compare(args.baseline.resolve(), args.iterations, args.warmup), indent=2))


if __name__ == "__main__":
    main()
