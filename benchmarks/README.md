# Wybthon benchmarks

The browser benchmark measures real Pyodide applications through delegated events. Run signal and transactional store modes separately:

```bash
uv sync --locked --group dev
uv run playwright install chromium
uv run python benchmarks/browser_bench.py --mode signal --json > signal.json
uv run python benchmarks/browser_bench.py --mode store --json > store.json
uv run python benchmarks/check_work.py store.json
```

To use the interactive app, run `wyb dev --dir .` and open `/benchmarks/app/index.html?mode=store`. Its source manifest requires the Wybthon server.

Each browser scenario restores its baseline, performs one warmup, then records three samples. It reports median synchronous commit time separately from input-to-frame time. Frame time is a requestAnimationFrame opportunity, not a precise paint completion measurement. DOM snapshots verify that each sample changes the UI.

| Scenario | Initial state | Result |
| --- | --- | --- |
| Create 1,000 | Empty | 1,000 rows |
| Replace 1,000 | 1,000 rows | 1,000 new rows |
| Create 10,000 | Empty | 10,000 rows |
| Update every tenth | 10,000 rows | 1,000 labels changed |
| Select | 10,000 rows | A different selected row |
| Swap | 10,000 rows | Rows 1 and 998 exchange positions |
| Remove | 10,000 rows | First row removed |
| Append | 10,000 rows | 11,000 rows |
| Clear | 10,000 rows | Empty |

The JSON includes runtime/browser metadata, individual samples, operation counters, and registry counts. Signal mode uses per-row label signals; store mode uses entity-preserving draft edits. Arbitrary replacement signal arrays still need list matching. Store edit records let the mounted list skip that scan for local updates.

`check_work.py` gates operation counts for store selection, swap, and append. CI saves both browser reports. Wall-clock results are observations, not portable pass/fail thresholds or cross-framework rankings. Run comparisons serially with the same browser, runtime, hardware, and cache conditions.

## Comparing checkouts

For a change that affects several operations, create an isolated baseline checkout and interleave it with the current code:

```bash
git worktree add --detach /tmp/wybthon-before <baseline-commit>
uv run python benchmarks/compare_browser.py --baseline /tmp/wybthon-before > signal-comparison.json
uv run python benchmarks/compare_browser.py --baseline /tmp/wybthon-before --mode store > store-comparison.json
```

Both checkouts run in separate pages of the same browser. Every operation restores its initial state, and the execution order alternates between samples. The default is one warmup and five measurements per operation. Avoid running other CPU-intensive work during comparisons; alternating order reduces drift but doesn't eliminate interference.

These comparisons invoke the Python operation directly and measure through its synchronous DOM commit. They also record a subsequent frame opportunity. They don't include delegated event dispatch and shouldn't be mixed with the event-driven timings above. DOM snapshots verify row counts and visible changes. `--profile` appends separate, untimed cProfile reports, and `--scenarios` selects specific operations.

For very short selection updates, `--scenarios select_toggle_10k --iterations 31` mounts each table once and then toggles between two rows, with a frame opportunity between samples. This measures repeated interaction separately from the first selection after constructing a fresh 10,000-row table. It isn't included in the default nine scenarios.

## Native benchmark

```bash
uv run python benchmarks/bench_runner.py --memory --json
```

This uses the Python DOM backend. It includes the nine collection operations plus reactive-hole and whole-tree-diff microbenchmarks. It isolates native Python behavior from WebAssembly and browser rendering; its times aren't browser predictions.

Use `--warmup`, `--iterations`, and `--bench` to focus a run. `--cpu --save report.json` records a comparison baseline, and `--cpu --compare report.json --threshold 0.15` compares best iterations. Create an isolated checkout for the baseline so measurement doesn't disturb ongoing changes.

`uv run python benchmarks/store_memory.py --repo /path/to/checkout` measures native Python allocations retained by a 10,000-entity store before any fields are observed. Inputs and imports are excluded. Compare fresh processes using the same interpreter; this is a tracemalloc measurement, not browser memory or process RSS.

## Startup

Generated production bundles expose `window.__WYB.timings`, including runtime loading, source archives, unpacking, application initialization, readiness, and a subsequent frame opportunity. Concurrent phases overlap. Startup is a separate measurement from these warmed collection scenarios. The production browser tests verify deep-link boot, lazy fetch timing, and development rebuild/reload.

The [runtime overhaul evaluation](results/runtime-overhaul.md) records local baseline comparisons, current store paths, and remaining mount costs.

The [performance follow-up](results/runtime-performance.md) records the subsequent optimizations, interleaved comparisons against both baselines, selection samples, and native store memory measurements.
