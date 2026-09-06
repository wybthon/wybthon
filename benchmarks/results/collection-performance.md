# Collection performance and memory

This evaluation compares the completed optimizations with `9fe61f6`, the repository's v0.33.0 baseline. Public signatures and production bundle formats are unchanged. The changes target avoidable allocation, persistent-list copying, matching-table construction, and reactive cleanup overhead.

## Changes

- Store entities with one parent share a weak reference to that parent. Reference counts preserve repeated occurrences, and entities with multiple parents use a weak dictionary. Membership and observed-index tables are allocated when needed. Field publication combines change detection and parent-link updates without repeatedly looking up the same values.
- Persistent vectors build leaves and branches directly. Tail deletion trims one tree path; general splices stream retained values into the new tree. Existing vector versions remain immutable, and append and indexed replacement retain structural sharing.
- `map_array` retains matching prefixes before allocating its matching table. It avoids unused item signals in identity mode, empty matching buckets for new rows, and unchanged index writes. Duplicate keys retain occurrence identity, and custom key functions run once per input item.
- `DraftList.clear()` records one clear edit instead of repeatedly popping items. Mounted lists process that edit together while preserving cleanup order from last to first, including clear-and-refill transactions held by an action. Pure list deletions skip an unused matching table.
- Default signal equality avoids a redundant callable check. Disposing synchronous computations and empty ownership scopes skips unused cleanup helpers.

## Native CPU and memory

These measurements use CPython 3.12.13 on Intel macOS, with two warmups and eleven measured samples per workload in fresh processes. The table reports median process CPU time. Setup, explicit garbage collection, verification, and disposal are outside each timing. Input values are prepared before measurement. These are native Python measurements, not browser latency predictions.

| Workload | Before, ms | After, ms | Time change |
| --- | ---: | ---: | ---: |
| Construct a 10,000-item vector | 12.342 | 0.172 | -98.6% |
| Remove the first vector item | 16.750 | 0.790 | -95.3% |
| Truncate a vector from 10,000 to 1,000 items | 12.228 | 0.014 | -99.9% |
| Create a 10,000-entity store | 92.689 | 38.381 | -58.6% |
| Clear 10,000 store entities through a draft | 95.613 | 5.909 | -93.8% |
| Update 1,000 observed store fields | 13.127 | 11.534 | -12.1% |
| Create a 10,000-item mapping | 30.699 | 19.324 | -37.1% |
| Append 1,000 mapped items to 10,000 | 20.160 | 5.627 | -72.1% |
| Remap 10,000 unchanged items | 17.644 | 4.142 | -76.5% |
| Reverse 10,000 mapped items | 19.788 | 18.035 | -8.9% |

An unobserved 10,000-entity store retained **16,257,080 bytes before and 5,536,328 bytes after**, a **65.9% reduction**. Peak traced allocations were 16,266,816 and 5,540,792 bytes. Inputs and imports are excluded. This measures Python allocations with `tracemalloc`, not process RSS, JavaScript heap usage, or WebAssembly memory capacity. Stores with extensively shared entities may see different savings.

The vector improvements reduce algorithmic work. Bulk construction and rebuilding become linear; truncation copies only a path instead of repeatedly popping each deleted item. Arbitrary arrays passed to `map_array` still require linear matching checks, including on append. Its gains come from reducing that work's allocation and propagation costs.

The existing native DOM benchmark also passed. Its raw report contains all eleven rendering workloads and heap measurements. Signal-table memory was unchanged: 17.54 MiB after mounting 1,000 rows and 23.88 MiB after five create/clear cycles. These measurements include the Python DOM stub and aren't browser memory measurements.

## Browser results

Chromium 151.0.7922.34 runs Pyodide 314.0.6 on Intel macOS. Each standard scenario restores its baseline, warms up once, and records five samples per checkout, alternating execution order. Times include Python work, serialization, and the synchronous DOM commit. DOM snapshots verify the visible result. All samples and subsequent frame opportunities are retained in the raw report.

### Signal arrays

| Operation | Before, ms | After, ms | Time change |
| --- | ---: | ---: | ---: |
| Create 1,000 | 89.0 | 90.7 | +1.9% |
| Replace 1,000 | 120.6 | 119.7 | -0.7% |
| Create 10,000 | 858.7 | 866.5 | +0.9% |
| Update every tenth of 10,000 | 10.0 | 9.7 | -3.0% |
| First selection among 10,000 | 1.0 | 0.3 | See selection note |
| Swap two of 10,000 | 21.1 | 21.4 | +1.4% |
| Remove first of 10,000 | 20.2 | 20.7 | +2.5% |
| Append 1,000 to 10,000 | 102.0 | 104.0 | +2.0% |
| Clear 10,000 by replacement | 436.4 | 417.1 | -4.4% |

### Transactional stores

| Operation | Before, ms | After, ms | Time change |
| --- | ---: | ---: | ---: |
| Create 1,000 | 115.9 | 111.4 | -3.9% |
| Replace 1,000 | 142.8 | 138.6 | -2.9% |
| Create 10,000 | 1147.7 | 1034.3 | -9.9% |
| Update every tenth of 10,000 | 32.3 | 34.7 | +7.4% |
| First selection among 10,000 | 0.4 | 1.0 | See selection note |
| Swap two of 10,000 | 0.6 | 0.6 | +0.0% |
| Remove first of 10,000 | 38.5 | 9.4 | -75.6% |
| Append 1,000 to 10,000 | 134.8 | 122.0 | -9.5% |
| Clear 10,000 by replacement | 447.1 | 445.0 | -0.5% |

### Draft clearing and timing follow-ups

The separate `set_store(lambda draft: draft.clear())` scenario measured **616.3 to 396.4 ms**, a **35.7% reduction**, with one warmup and five samples per checkout. It removes the same 10,000 rows as whole-list replacement while exercising the draft mutation API. Regression tests require one edit, one commit, deferred disposal until the update becomes visible, and the original cleanup order.

First-selection timings are too short and variable for a useful percentage comparison. In separate 31-sample runs that mount each table once, repeated selection measured **0.4 to 0.4 ms in both modes**, with two DOM commands per toggle.

The five-sample store field-update result was slower in the main table. An eleven-sample follow-up measured **29.7 to 29.1 ms (-2.0%)**, with overlapping ordinary samples and one long pause in each checkout. Separate, untimed profiles reduced Python calls from 113,079 to 105,079. These results support reduced work but don't establish a large browser latency improvement for this operation.

The native whole-tree rerender result also varied: its full-suite means were 8.37 and 9.80 ms. Two isolated 21-sample comparisons, with checkout order reversed in the second pair, averaged **8.23 and 8.21 ms** across the equally sized runs. The raw report retains both the initial result and the follow-ups. Don't interpret small or short-run timing differences as portable speed guarantees.

### Frame opportunities

These medians include a subsequent `requestAnimationFrame` opportunity. They don't guarantee completed layout or paint and can vary with frame scheduling. They are separate from synchronous commit time.

| Operation | Signal before, ms | Signal after, ms | Store before, ms | Store after, ms |
| --- | ---: | ---: | ---: | ---: |
| Create 1,000 | 110.5 | 113.3 | 140.8 | 135.2 |
| Replace 1,000 | 122.0 | 120.4 | 160.7 | 139.4 |
| Create 10,000 | 1164.1 | 1180.1 | 1582.2 | 1537.0 |
| Update every tenth of 10,000 | 11.8 | 10.8 | 44.0 | 41.5 |
| First selection among 10,000 | 12.7 | 5.5 | 11.8 | 12.6 |
| Swap two of 10,000 | 21.9 | 36.9 | 7.3 | 8.5 |
| Remove first of 10,000 | 21.3 | 21.3 | 46.4 | 12.6 |
| Append 1,000 to 10,000 | 173.7 | 172.1 | 217.0 | 225.3 |
| Clear 10,000 by replacement | 437.3 | 418.8 | 448.8 | 445.9 |

## Startup and bundle size

The compressed production runtime archive grew from **149,314 to 150,445 bytes**, an increase of **1,131 bytes, or 0.76%**. Runtime Python sources grew from 494,234 to 498,845 bytes. The bootstrap, Pyodide version, application bundle, and bundle format are unchanged.

Production startup uses the same generated counter application in both checkouts, one warmup per checkout, and five measured boots in alternating order. Each navigation creates a fresh Pyodide runtime with a warmed shared HTTP cache. Every sample verifies the initial UI and a working counter event. These aren't cold-network transfer measurements.

| Startup phase | Before, ms | After, ms |
| --- | ---: | ---: |
| Fetch source archives | 17.1 | 16.4 |
| Load and initialize Pyodide | 1530.8 | 1536.6 |
| Unpack archives | 16.5 | 16.4 |
| Import and initialize application | 270.1 | 268.5 |
| Ready | 1823.4 | 1815.3 |
| Ready plus frame opportunity | 1833.9 | 1817.1 |

Startup remained comparable. Concurrent phases overlap, so the individual phase durations shouldn't be added together.

## Compatibility and work checks

All **476 unit tests pass on Python 3.12.13 and 3.14.5**, and all **60 browser tests pass**. Ruff, Black, mypy, and the strict documentation build pass. Unit coverage, including branches, is **82.04%**. Eighteen added regression cases cover tree-size boundaries, immutable historical vectors, shared and repeated store entities, weak parent lifetimes, duplicate mapped keys, replacement values, callback counts, reactive indices, transactional draft clearing, and cleanup order during a held clear-and-refill operation. Existing transition, optimistic state, ownership, error, event, form, router, and production-build checks also pass.

The delegated browser work gates pass: selection creates no rows and emits one command; swapping creates no rows and emits two commands; appending creates exactly 1,000 rows with 1,000 template recipe hits and 7,000 commands in one commit. None of those store operations scans the full list. Registry lifetime checks remain covered by the browser suite.

## Reproduction

```bash
git worktree add --detach /tmp/wybthon-before 9fe61f6
uv run python benchmarks/core_bench.py --repo /tmp/wybthon-before --iterations 11 > core-before.json
uv run python benchmarks/core_bench.py --iterations 11 > core-after.json
uv run python benchmarks/compare_browser.py --baseline /tmp/wybthon-before > signal.json
uv run python benchmarks/compare_browser.py --baseline /tmp/wybthon-before --mode store > store.json
uv run python benchmarks/compare_browser.py --baseline /tmp/wybthon-before --mode store --scenarios clear_draft_10k > clears.json
uv run python benchmarks/compare_browser.py --baseline /tmp/wybthon-before --mode store --scenarios update_10th_10k --iterations 11 --profile > updates.json
uv run python benchmarks/compare_startup.py --baseline /tmp/wybthon-before > startup.json
uv run python benchmarks/browser_bench.py --mode store --json > work.json
uv run python benchmarks/check_work.py work.json
```

For the selection follow-ups, use `--scenarios select_toggle_10k --iterations 31` in each mode. For native whole-tree rendering, run `bench_runner.py --cpu --bench 'full rerender' --warmup 3 --iterations 21` in fresh processes with `PYTHONPATH` set to each checkout's `src` directory, then reverse the checkout order and repeat.

Run comparisons serially using the same interpreter, browser, hardware, and cache conditions. Reverse checkout order when investigating small native timing differences. All browser comparison reports were checked against the final Python source fingerprint. Raw reports and environment metadata are in [collection-performance.json](collection-performance.json); additional measurement details are in the [benchmark guide](../README.md).

These results don't establish a universal speedup. Large unvirtualized mounts still allocate and wire each visible row, and startup still includes loading and initializing Pyodide. Browser heap usage, process RSS, cold-network startup, and exact paint completion weren't measured.
