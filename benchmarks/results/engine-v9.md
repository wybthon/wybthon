# Engine v9 evaluation

This evaluation compares [RFC 0010](../../docs/rfcs/0010-engine-v9.md) with v0.44.0 (`1fffede`). What changed in the engine:

- a component tag mounts the template its body returns straight into its slot, and a list of one child mounts as that child;
- a `Show`, `For`, `Repeat`, `Switch`, or unkeyed fragment that fills a slot or a hole ends at its anchor and has no markers;
- a server-rendered template instance hydrates with one `CLAIM_TPL` command, plus one `CLAIM_SLOT` per slot holding nodes;
- plain signal writes, template binding applies, `_read`, and static probes take shorter paths, and a template expression found reactive once isn't probed again.

## Measurement conditions

An Apple M-series laptop (arm64) on macOS. Native runs used CPython 3.14.5, alternating the two checkouts in fresh processes, three rounds for `component_bench.py` and two for the others, best times shown. Browser runs used Chromium 151.0.7922.34 with Pyodide 314.0.6 (Python 3.14.2), `compare_browser.py`'s default of one warmup and five alternating samples per operation, medians shown. Command and call counts are deterministic.

## Components and control flow

`benchmarks/component_bench.py` mounts 1,000 rows showing the same markup four ways: inline in the row's template, inline with a `Show` in it, as a component tag (`<{Card} ...><em>...</em></{Card}>`), and as a component tag whose body has a `Show`.

| Row | Create, v0.44.0 | Create, Engine v9 | Calls per row | Commands per row | Bytes per row | Clear, v0.44.0 | Clear, Engine v9 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Inline markup | 2.82 ms | 2.82 ms | 41 → 35 | 1 → 1 | 986 → 986 | 0.51 ms | 0.51 ms |
| Inline markup with a `Show` | 6.14 ms | 5.28 ms | 97 → 71 | 5 → 1 | 2,890 → 2,826 | 1.35 ms | 1.31 ms |
| The markup in a component | 7.77 ms | 5.80 ms | 134 → 79 | 6 → 2 | 3,378 → 3,002 | 1.49 ms | 1.34 ms |
| A component with a `Show` | 11.40 ms | 8.53 ms | 190 → 115 | 10 → 2 | 5,282 → 4,842 | 2.51 ms | 2.34 ms |

A component row now costs 2.1 times the same markup inlined, where it cost 2.8 times, and two commands, one clone for the card and one for its child, where it cost six. A `Show` that fills a slot costs no commands at all: it used to create and insert two comment markers. Python calls per component row fell by 41%.

What's left is mostly what composition is: a second template to clone and fill, the component's owner and props, the getters the parent passes, and the child's template. The inline row also got cheaper (41 to 35 calls), from probes that return a static value without consulting the accessor rule.

## Hydration

The same tables, rendered on the server and hydrated into the in-memory document of `wybthon.testing`:

| Table | Commands per row, v0.44.0 | Engine v9 | Time, v0.44.0 | Engine v9 | Mismatches |
| --- | ---: | ---: | ---: | ---: | ---: |
| Inline markup | 10.01 | 1.01 | 25.5 ms | 19.2 ms | 0 |
| The markup in a component | 13.01 | 3.01 | 38.7 ms | 27.5 ms | 0 |

A server-rendered row now costs one command, as a client-rendered one does. The component row's three are the card's claim, one slot claim for its child, and the child's claim. Attribute bindings no longer resend the values the server wrote, so a row of the js-framework-benchmark table, with its dynamic `class`, hydrates in one command too. The times include the reference backend's own DOM work in Python, which the browser does natively, so they understate the change; browser hydration wasn't timed.

## Browser

`benchmarks/compare_browser.py`, with a new `component` mode in the benchmark app that renders each row with a component tag (`BenchRow`), the same app for both checkouts. Median synchronous work through the DOM commit, in milliseconds:

| Operation | Component, v0.44.0 | Component, Engine v9 | Signal, v0.44.0 | Signal, Engine v9 | Store, v0.44.0 | Store, Engine v9 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Create 1,000 | 21.1 | 19.1 | 21.3 | 21.8 | 24.7 | 23.2 |
| Replace 1,000 | 27.5 | 25.7 | 25.0 | 26.0 | 49.4 | 49.5 |
| Create 10,000 | 200.1 | 184.1 | 135.0 | 132.4 | 197.1 | 188.3 |
| Update every tenth of 10,000 | 5.3 | 5.2 | 5.5 | 4.9 | 13.3 | 13.4 |
| Select a row of 10,000 | 0.3 | 0.2 | 0.3 | 0.3 | 0.3 | 0.3 |
| Swap two of 10,000 | 3.8 | 4.3 | 6.0 | 5.8 | 1.1 | 1.1 |
| Remove the first of 10,000 | 7.6 | 7.0 | 8.8 | 9.1 | 5.2 | 4.5 |
| Append 1,000 to 10,000 | 27.7 | 26.2 | 24.7 | 25.8 | 27.0 | 27.1 |
| Clear 10,000 | 76.9 | 71.8 | 79.3 | 75.1 | 110.3 | 103.5 |

Component rows mount 5% to 10% faster and clear 7% faster. The benchmark's `BenchRow` has no children and no `Show`, so it gains only the component's own mounting, not the markers that `component_bench.py`'s rows also lose. Swapping two component rows measured 0.5 ms slower; a swap is two native moves and the same Python work on both sides, and the signal-mode swap measured faster, so this reads as noise, but it wasn't re-measured. Signal and store rows are otherwise unchanged within the comparison's noise (five samples per side put a few percent either way within it), apart from faster updates in signal mode and faster creation and clearing in store mode.

## Rows and the core

`benchmarks/row_bench.py`, best of two alternating runs, milliseconds:

| Operation | v0.44.0 | Engine v9 |
| --- | ---: | ---: |
| Create 1,000 rows | 4.13 | 4.19 |
| Create 10,000 rows | 43.21 | 43.68 |
| Clear 10,000 rows | 14.36 | 14.07 |
| Update every tenth of 10,000 | 1.41 | 1.25 |
| Swap two of 10,000 | 0.90 | 0.88 |
| Append 1,000 to 10,000 | 4.87 | 4.94 |

Unchanged within noise but for updates, 11% faster from the plain write path and the binding apply path. Creating 1,000 rows makes 61,092 Python calls (61,098 before) and keeps 2,464 bytes and 15.0 tracked objects per row, as before.

Core operations, microseconds per operation, best of seven:

| Operation | v0.44.0 | Engine v9 |
| --- | ---: | ---: |
| Write and flush, one render effect | 1.46 | 1.38 |
| Write and flush, one user effect | 1.60 | 1.54 |
| Write and flush, a memo read by 100 render effects | 80.2 | 80.9 |
| Write and flush, a chain of 100 memos | 62.4 | 62.3 |
| Create and dispose a render effect | 1.47 | 1.48 |
| Create a memo | 1.33 | 1.33 |
| Create a signal | 0.23 | 0.24 |
| An empty `flush()` | 0.15 | 0.15 |

The fast paths take about 5% off a plain write and flush; creating computations and propagating through memos are unchanged, since that cost is the transition engine's general bookkeeping (see the RFC's unresolved questions).

## Stores

The row of `component_bench`'s inline table without its button, 10,000 rows, best of two alternating runs:

| Operation | v0.44.0 | Engine v9 |
| --- | ---: | ---: |
| Create, a store | 56.6 ms | 49.2 ms |
| Update every tenth, a store | 3.00 ms | 2.94 ms |
| Create, per-row signals | 30.8 ms | 31.5 ms |
| Update every tenth, per-row signals | 1.16 ms | 1.07 ms |

Store rows mount 13% faster: a field binding's probe ran once per row, read the field, and escaped with an exception before the binding read it again; now only the first row's expression is probed.

## Validation

- **Unit tests:** 3,236 pass on Python 3.14 (one pyright test skips without pyright), with 82% branch coverage, including `tests/test_engine_v9.py` and a zero-mismatch hydration check over `tests/test_ssr_output.py`'s views.
- **Typing and lint:** mypy, ruff, and the formatter pass.
- **Browser tests:** 95 pass in Chromium on Pyodide 314.0.6, including the hydration and full-stack suites, which run the JavaScript kernel's `CLAIM_TPL` walk.

## Reproduction

```bash
git worktree add --detach /tmp/wybthon-before 1fffede
cp benchmarks/app/bench/main.py /tmp/wybthon-before/benchmarks/app/bench/main.py
uv run python benchmarks/component_bench.py /tmp/wybthon-before/src --reps 7
uv run python benchmarks/component_bench.py src --reps 7
uv run python benchmarks/row_bench.py /tmp/wybthon-before/src --reps 7
uv run python benchmarks/row_bench.py src --reps 7
uv run python benchmarks/compare_browser.py --baseline /tmp/wybthon-before --mode component
uv run python benchmarks/compare_browser.py --baseline /tmp/wybthon-before --mode signal
uv run python benchmarks/compare_browser.py --baseline /tmp/wybthon-before --mode store
```

The benchmark app's `component` mode is new, so the baseline checkout gets the current app (the second line). The core and store tables came from scratch scripts that aren't committed; the tables above are the record of this evaluation.
