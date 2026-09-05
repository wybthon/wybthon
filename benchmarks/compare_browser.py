"""Interleave identical browser operations against two repository checkouts.

Synchronous timings include Python work, JSON serialization, and native kernel
application. Frame timings include a subsequent requestAnimationFrame opportunity,
not a guarantee of completed paint. Each sample restores its baseline, and the
execution order alternates to reduce bias from machine load and thermal drift.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import platform
import statistics
import subprocess
import sys
from pathlib import Path

from browser_bench import APP_URL_PATH, BOOT_TIMEOUT_MS, REPO_ROOT, _free_port, _wait_for_http
from playwright.sync_api import sync_playwright

SCENARIOS = {
    "create_1k": ("clear()", "run()", 1000),
    "replace_1k": ("clear(); run()", "run()", 1000),
    "create_10k": ("clear()", "run_lots()", 10000),
    "update_10th_10k": ("clear(); run_lots()", "update()", 10000),
    "select_10k": ("clear(); run_lots()", 'select(data()[0]["id"])', 10000),
    "swap_10k": ("clear(); run_lots()", "swap_rows()", 10000),
    "remove_10k": ("clear(); run_lots()", 'delete(data()[0]["id"])', 9999),
    "append_to_10k": ("clear(); run_lots()", "add()", 11000),
    "clear_10k": ("clear(); run_lots()", "clear()", 0),
    "select_toggle_10k": (
        "clear(); run_lots()",
        'select(data()[0]["id"] if selected() != data()[0]["id"] else data()[1]["id"])',
        10000,
    ),
}

INSTRUMENTATION = """
import json, time, sys, pyodide
from wybthon import kernel as _perf_kernel
_perf_backend = _perf_kernel._backend
_perf_samples = []
def _perf_apply(ops):
    started = time.perf_counter()
    encoded = json.dumps(ops, separators=(",", ":"), ensure_ascii=False)
    serialized = time.perf_counter()
    _perf_backend._kernel.apply(encoded)
    finished = time.perf_counter()
    _perf_samples.append({"serialize_ms": (serialized-started)*1000,
                          "kernel_ms": (finished-serialized)*1000,
                          "dom_ops": len(ops), "serialized_bytes": len(encoded)})
_perf_backend.apply = _perf_apply
def _perf_run(code):
    _perf_samples.clear()
    started = time.perf_counter()
    exec(code)
    elapsed = (time.perf_counter()-started)*1000
    result = {key: sum(sample[key] for sample in _perf_samples)
              for key in ("serialize_ms", "kernel_ms", "dom_ops", "serialized_bytes")}
    result["sync_commit_ms"] = elapsed
    result["python_ms"] = elapsed-result["serialize_ms"]-result["kernel_ms"]
    result["commits"] = len(_perf_samples)
    return json.dumps(result)
"""

SNAPSHOT = """() => {
  const rows = document.querySelector('#tbody').rows;
  return {count: rows.length, rows: [0, 1, 10, 998, rows.length-1].map(i =>
    rows[i] ? [rows[i].textContent, rows[i].className] : null)};
}"""


@contextlib.contextmanager
def serve(repo):
    port = _free_port()
    env = dict(os.environ, PYTHONPATH=str(repo / "src"))
    server = subprocess.Popen(
        [sys.executable, "-m", "wybthon.dev", "dev", "--port", str(port), "--dir", str(repo)],
        cwd=repo,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}{APP_URL_PATH}"
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


def python(page, code):
    return page.evaluate("code => window._pyodide.runPython(code)", code)


def revision(repo):
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()


def source_digest(repo):
    digest = hashlib.sha256()
    for source in sorted((repo / "src" / "wybthon").rglob("*.py")):
        digest.update(str(source.relative_to(repo)).encode())
        digest.update(source.read_bytes())
    return digest.hexdigest()


def compare(baseline, mode, iterations, warmup, names, cpu_profile):
    with contextlib.ExitStack() as stack:
        urls = [stack.enter_context(serve(repo)) for repo in (baseline, REPO_ROOT)]
        playwright = stack.enter_context(sync_playwright())
        browser = playwright.chromium.launch()
        stack.callback(browser.close)
        pages = {}
        for side, url in zip(("before", "after"), urls, strict=True):
            page = pages[side] = browser.new_page()
            page.goto(f"{url}?mode={mode}")
            page.wait_for_selector("#bench-panel", state="visible", timeout=BOOT_TIMEOUT_MS)
            python(page, INSTRUMENTATION)
        result = {
            "metadata": {
                "baseline": revision(baseline),
                "current_base": revision(REPO_ROOT),
                "source_sha256": {"before": source_digest(baseline), "after": source_digest(REPO_ROOT)},
                "current_dirty": bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=REPO_ROOT)),
                "platform": platform.platform(),
                "browser": browser.version,
                "runtime": json.loads(python(pages["after"], "json.dumps([sys.version, pyodide.__version__])")),
                "mode": mode,
                "iterations": iterations,
                "warmup": warmup,
                "method": "alternating direct Python operations",
                "baseline_policy": {
                    name: "once per checkout" if name == "select_toggle_10k" else "before each sample" for name in names
                },
            },
            "scenarios": {},
        }
        for name in names:
            setup, operation, expected = SCENARIOS[name]
            samples: dict[str, list[dict]] = {"before": [], "after": []}
            for iteration in range(warmup + iterations):
                order = ("before", "after") if iteration % 2 == 0 else ("after", "before")
                for side in order:
                    page = pages[side]
                    page.bring_to_front()
                    if name != "select_toggle_10k" or iteration == 0:
                        python(page, setup)
                    page.evaluate("() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")
                    before = page.evaluate(SNAPSHOT)
                    sample = page.evaluate(
                        """async code => {
                          const started = performance.now();
                          const result = JSON.parse(window._pyodide.runPython(code));
                          await new Promise(r => requestAnimationFrame(r));
                          result.input_to_frame_ms = performance.now()-started;
                          return result;
                        }""",
                        f"_perf_run({operation!r})",
                    )
                    after = page.evaluate(SNAPSHOT)
                    assert after["count"] == expected, (name, side, after)
                    assert before != after, (name, side, "operation didn't change the DOM")
                    if iteration >= warmup:
                        samples[side].append(sample)
            summary = {}
            for side, values in samples.items():
                summary[side] = {key: statistics.median(sample[key] for sample in values) for key in values[0]}
                summary[side]["samples"] = values
            summary["change_percent"] = (
                summary["after"]["sync_commit_ms"] / summary["before"]["sync_commit_ms"] - 1
            ) * 100
            result["scenarios"][name] = summary
            print(
                f"{name}: {summary['before']['sync_commit_ms']:.1f} -> "
                f"{summary['after']['sync_commit_ms']:.1f} ms ({summary['change_percent']:+.1f}%)",
                file=sys.stderr,
                flush=True,
            )
        if cpu_profile:
            for side, page in pages.items():
                python(page, "import cProfile, pstats, io")
                profiles = {}
                for name in names:
                    setup, operation, _ = SCENARIOS[name]
                    python(page, setup)
                    if name == "select_toggle_10k":
                        python(page, 'select(data()[0]["id"])')
                    profiles[name] = python(
                        page,
                        "_prof = cProfile.Profile()\n"
                        f"_prof.runcall(lambda: exec({operation!r}))\n"
                        "_stream = io.StringIO()\n"
                        "pstats.Stats(_prof, stream=_stream).strip_dirs().sort_stats('cumulative').print_stats(35)\n"
                        "_stream.getvalue()",
                    )
                result[side + "_profiles"] = profiles
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True, help="Isolated baseline checkout")
    parser.add_argument("--mode", choices=["signal", "store"], default="signal")
    parser.add_argument("--iterations", type=int, default=5)
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument(
        "--scenarios", nargs="+", choices=SCENARIOS, default=[name for name in SCENARIOS if name != "select_toggle_10k"]
    )
    parser.add_argument("--profile", action="store_true", help="Record untimed cProfile reports afterward")
    args = parser.parse_args()
    if args.iterations < 1 or args.warmup < 0:
        parser.error("iterations must be positive and warmup nonnegative")
    print(
        json.dumps(
            compare(args.baseline.resolve(), args.mode, args.iterations, args.warmup, args.scenarios, args.profile),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
