# Engine v2 evaluation

This evaluation compares [RFC 0002](../../docs/rfcs/0002-engine-v2.md) with v0.36.0 (`ecaf7bd`). The Virtual DOM, delegated events, and batched JavaScript kernel remain. What changed is how much Python work each mounted node costs and how many commands cross the bridge.

## Changes measured here

- Each repeated subtree shape compiles to a generated mount function. One fused `CLONE` command clones a row's skeleton, fills its text slots (including its label hole's first value), marks its delegated listeners, and inserts it.
- Unmounting releases native nodes inside the kernel (`DISPOSE_RANGE`) instead of sending every id from Python. Clearing a list is one command.
- List rows and component output release their static VNodes once mounted, because they're never patched.
- Render bindings run their expression directly, and a re-running computation keeps the dependency edges it reads again instead of unsubscribing and resubscribing.
- Selection uses a projection (Solid 2.0 removed `createSelector`), and stores load on first use.

## Native Python cost

`benchmarks/row_bench.py` runs the js-framework-benchmark table in CPython 3.14.8 on Intel macOS. The backend JSON-encodes every command batch but applies nothing, so each time is Python's share of the browser work. The two checkouts alternated across fresh processes; the tables report the minimum process CPU time. The machine was under heavy unrelated load during parts of these runs, so compare the columns within a row rather than absolute times.

The idiomatic table, with each version's selection primitive (`create_selector` before, a projection after):

| Operation | Before, ms | After, ms | Speedup | Commands before | Commands after |
| --- | ---: | ---: | ---: | ---: | ---: |
| Create 1,000 | 64.6 | 44.7 | 1.44x | 7,000 | 1,000 |
| Replace 1,000 | 79.8 | 53.6 | 1.49x | 9,000 | 1,001 |
| Create 10,000 | 689.4 | 470.9 | 1.46x | 70,000 | 10,000 |
| Append 1,000 to 10,000 | 72.0 | 49.8 | 1.44x | 7,000 | 1,000 |
| Clear 1,000 | 12.5 | 6.4 | 1.96x | 2 | 1 |
| Clear 10,000 | 139.2 | 68.1 | 2.04x | 2 | 1 |
| Update every tenth of 10,000 | 5.4 | 5.3 | 1.03x | 1,000 | 1,000 |
| Select among 10,000 | 0.12 | 0.17 | 0.71x | 2 | 2 |
| Swap two of 10,000 | 9.3 | 8.3 | 1.11x | 2 | 2 |
| Remove first of 10,000 | 7.4 | 7.0 | 1.05x | 2 | 1 |

Without the selection binding, which isolates the rendering engine:

| Operation | Before, ms | After, ms | Speedup |
| --- | ---: | ---: | ---: |
| Create 1,000 | 62.1 | 34.3 | 1.81x |
| Replace 1,000 | 77.0 | 40.8 | 1.89x |
| Create 10,000 | 687.3 | 364.1 | 1.89x |
| Append 1,000 to 10,000 | 64.2 | 40.9 | 1.57x |
| Clear 1,000 | 11.7 | 5.0 | 2.34x |
| Clear 10,000 | 123.7 | 49.7 | 2.49x |

A mounted row retains **5,955 bytes instead of 10,723 (44% less)** with selection, and 5,379 instead of 9,568 without it, measured with `tracemalloc` after a collection. Fewer live objects also means less work for every later cyclic collection.

Selection is the one regression. A projection recomputes a small store (a session, a merge, and a publish) where `create_selector` flipped two flags. It still notifies only the two affected rows and sends two commands, at about 0.05 ms more per selection natively. It's the Solid 2.0 pattern, and it handles any derived shape, not just booleans.

## Browser

`benchmarks/compare_browser.py` alternated the two checkouts in Chromium with Pyodide 314.0.6, seven samples per operation. The machine's load average was between 120 and 350 during these runs, far above its core count, so these are the least reliable numbers here. The raw reports keep every sample.

| Operation | Signal before, ms | Signal after, ms | Store before, ms | Store after, ms |
| --- | ---: | ---: | ---: | ---: |
| Create 1,000 | 156.0 | 121.9 | 179.5 | 147.4 |
| Replace 1,000 | 417.8 | 314.8 | 334.9 | 222.1 |
| Create 10,000 | 1,594.0 | 1,821.6 | 3,029.9 | 1,961.4 |
| Append 1,000 to 10,000 | 172.0 | 143.0 | 314.5 | 211.0 |
| Update every tenth of 10,000 | 24.9 | 20.5 | 48.0 | 50.5 |
| Clear 10,000 | 567.5 | 510.7 | 1,568.0 | 1,411.3 |
| Select among 10,000 | 0.5 | 0.7 | 0.6 | 1.0 |

Create, replace, and append improved by 15 to 35% in both modes; the 10,000-row creates moved in opposite directions between modes, which is consistent with the noise. Every row now sends one command instead of seven, and the payload shrinks accordingly. Large browser timings are dominated by the cyclic collector and by WebAssembly memory growth once tens of thousands of objects are live, which affects both versions; in a direct probe after the page went idle, updating every tenth row took about 40 ms in both versions, with occasional collection spikes in each.

Rerun the browser comparison on an idle machine before quoting these numbers.

## Startup

`benchmarks/compare_startup.py` booted the generated starter application six times per checkout with a warm HTTP cache. Importing and initializing the application fell from **402.5 to 160.1 ms (60% less)**, because the package no longer imports the router, forms, virtual lists, or stores at startup. Loading Pyodide itself varied too much under the machine's load to compare.

## Validation

- 726 unit tests pass on Python 3.14, with 86% branch coverage.
- 71 browser tests pass, including hydration, `NoHydration`, production builds with dev mode off, and the kernel protocol (one `CLONE` per row, no `LISTEN`, one `DISPOSE_RANGE` per clear, registries back at baseline).
- Ruff, mypy, pyright on the typing fixtures, and the strict documentation build pass.
- `benchmarks/check_work.py` gates one command per appended row and one command per clear.

## Reproduction

```bash
git worktree add --detach /tmp/wybthon-before ecaf7bd
uv run python benchmarks/row_bench.py /tmp/wybthon-before/src --reps 5 > rows-before.json
uv run python benchmarks/row_bench.py src --reps 5 > rows-after.json
uv run python benchmarks/row_bench.py src --reps 5 --noselect > rows-engine.json
uv run --group dev python benchmarks/compare_browser.py --baseline /tmp/wybthon-before --iterations 7 > signal.json
uv run --group dev python benchmarks/compare_browser.py --baseline /tmp/wybthon-before --mode store --iterations 7 > store.json
uv run --group dev python benchmarks/compare_startup.py --baseline /tmp/wybthon-before > startup.json
```

Raw reports: [native](engine-v2-native.json), [browser, signal mode](engine-v2-browser-signal.json), [browser, store mode](engine-v2-browser-store.json), and [startup](engine-v2-startup.json).

## What's left

The largest remaining cost in creating rows is building their VNode trees in application code: about a third of the time, now that mounting itself is cheap. A build-time compiler that turns static `div(...)` trees into template factories (deferred in RFC 0002) would remove most of it. Moving rarely used computation fields into a side record would shrink each binding further.
