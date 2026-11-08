# Engine v9 evaluation

This evaluation compares [RFC 0010](../../docs/rfcs/0010-engine-v9.md) with v0.44.0 (`1fffede`). What changed in the engine:

- a component tag mounts the template its body returns straight into its slot, and in a template that's never patched a child slot holding a list of one node mounts that node without a fragment;
- a `Show`, `For`, `Repeat`, `Switch`, or unkeyed fragment that fills a slot or a hole ends at its anchor and has no markers;
- a server-rendered template instance hydrates with one `CLAIM_TPL` command, which carries its attribute values, plus one `CLAIM_SLOT` per slot holding nodes;
- plain signal writes, template binding applies, `_read`, and static probes take shorter paths, and a template expression found reactive once isn't probed again.

## Measurement conditions

An Apple M-series laptop (arm64) on macOS. Native runs used CPython 3.14.5, alternating the two checkouts in fresh processes, three rounds for `component_bench.py` and two for the others, best times shown. Browser runs used Chromium 151.0.7922.34 with Pyodide 314.0.6 (Python 3.14.2), `compare_browser.py`'s default of one warmup and five alternating samples per operation, medians shown. Command and call counts are deterministic.

## Components and control flow

`benchmarks/component_bench.py` mounts 1,000 rows showing the same markup four ways: inline in the row's template, inline with a `Show` in it, as a component tag (`<{Card} ...><em>...</em></{Card}>`), and as a component tag whose body has a `Show`.

| Row | Create, v0.44.0 | Create, Engine v9 | Calls per row | Commands per row | Bytes per row | Clear, v0.44.0 | Clear, Engine v9 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Inline markup | 2.81 ms | 2.84 ms | 41 → 35 | 1 → 1 | 986 → 986 | 0.51 ms | 0.52 ms |
| Inline markup with a `Show` | 6.15 ms | 5.30 ms | 97 → 71 | 5 → 1 | 2,890 → 2,826 | 1.34 ms | 1.34 ms |
| The markup in a component | 7.78 ms | 5.95 ms | 134 → 84 | 6 → 2 | 3,378 → 3,002 | 1.50 ms | 1.37 ms |
| A component with a `Show` | 11.40 ms | 8.67 ms | 190 → 120 | 10 → 2 | 5,282 → 4,842 | 2.52 ms | 2.37 ms |

A component row now costs 2.1 times the same markup inlined, where it cost 2.8 times, and two commands, one clone for the card and one for its child, where it cost six. A `Show` that fills a slot costs no commands at all: it used to create and insert two comment markers. Python calls per component row fell by 37%.

What's left is mostly what composition is: a second template to clone and fill, the component's owner and props, the getters the parent passes, and the child's template. The inline row also got cheaper (41 to 35 calls), from probes that return a static value without consulting the accessor rule.

## Hydration

The same tables, rendered on the server and hydrated into the in-memory document of `wybthon.testing`:

| Table | Commands per row, v0.44.0 | Engine v9 | Time, v0.44.0 | Engine v9 | Mismatches |
| --- | ---: | ---: | ---: | ---: | ---: |
| Inline markup | 10.01 | 1.01 | 25.8 ms | 19.3 ms | 0 |
| The markup in a component | 13.01 | 3.01 | 39.6 ms | 29.0 ms | 0 |

A server-rendered row now costs one command, as a client-rendered one does. The component row's three are the card's claim, one slot claim for its child, and the child's claim. Attribute bindings send their values inside the claim, which writes only those that differ from the server's, so a row of the js-framework-benchmark table, with its dynamic `class`, hydrates in one command too, and a value only the browser computes is still corrected. The times include the reference backend's own DOM work in Python, which the browser does natively, so they understate the change; browser hydration wasn't timed.

## Browser

`benchmarks/compare_browser.py`, with a new `component` mode in the benchmark app that renders each row with a component tag (`BenchRow`), the same app for both checkouts. Median synchronous work through the DOM commit, in milliseconds:

| Operation | Component, v0.44.0 | Component, Engine v9 | Signal, v0.44.0 | Signal, Engine v9 | Store, v0.44.0 | Store, Engine v9 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Create 1,000 | 20.6 | 18.6 | 12.2 | 12.9 | 15.1 | 14.4 |
| Replace 1,000 | 27.2 | 25.0 | 17.8 | 18.2 | 21.3 | 20.9 |
| Create 10,000 | 200.1 | 178.4 | 120.3 | 122.9 | 148.1 | 140.3 |
| Update every tenth of 10,000 | 5.2 | 4.8 | 3.8 | 3.5 | 8.0 | 7.7 |
| Select a row of 10,000 | 0.3 | 0.3 | 0.2 | 0.3 | 0.3 | 0.3 |
| Swap two of 10,000 | 3.6 | 4.3 | 3.6 | 3.6 | 0.7 | 0.7 |
| Remove the first of 10,000 | 5.9 | 6.8 | 4.2 | 4.3 | 3.3 | 2.7 |
| Append 1,000 to 10,000 | 23.7 | 21.3 | 16.7 | 15.9 | 18.5 | 17.3 |
| Clear 10,000 | 65.9 | 66.5 | 55.2 | 56.7 | 83.8 | 80.2 |

Component rows mount 8% to 11% faster and update 8% faster. The benchmark's `BenchRow` has no children and no `Show`, so it gains only the component's own mounting, not the markers that `component_bench.py`'s rows also lose. Swapping two component rows measured 0.7 ms slower, and an earlier run of the same comparison measured it 0.5 ms slower, so it's likely real rather than noise; a swap is two native moves and the same Python work on both sides, and the cause hasn't been found. Removing the first component row measured 0.9 ms slower here and faster in the earlier run. Signal and store rows are otherwise unchanged within the comparison's noise (five samples per side put a few percent either way within it), apart from faster updates in both modes and faster store creation.

## Rows and the core

`benchmarks/row_bench.py`, best of two alternating runs, milliseconds:

| Operation | v0.44.0 | Engine v9 |
| --- | ---: | ---: |
| Create 1,000 rows | 4.11 | 4.18 |
| Create 10,000 rows | 42.86 | 43.90 |
| Clear 10,000 rows | 14.46 | 14.55 |
| Update every tenth of 10,000 | 1.45 | 1.36 |
| Swap two of 10,000 | 0.90 | 0.90 |
| Append 1,000 to 10,000 | 4.87 | 5.16 |

Updates are 6% faster, from the plain write path and the binding apply path. Creating rows measured 2% slower and appending 6% slower, though a row makes the same Python calls: creating 1,000 rows makes 61,094 (61,098 before) and keeps 2,464 bytes and 15.0 tracked objects per row, as before.

Core operations, microseconds per operation, best of seven:

| Operation | v0.44.0 | Engine v9 |
| --- | ---: | ---: |
| Write and flush, one render effect | 1.46 | 1.42 |
| Write and flush, one user effect | 1.60 | 1.57 |
| Write and flush, a memo read by 100 render effects | 80.2 | 80.8 |
| Write and flush, a chain of 100 memos | 62.9 | 62.6 |
| Create and dispose a render effect | 1.46 | 1.46 |
| Create a memo | 1.33 | 1.34 |
| Create a signal | 0.23 | 0.23 |
| An empty `flush()` | 0.15 | 0.15 |

The fast paths take about 2% to 3% off a plain write and flush; creating computations and propagating through memos are unchanged, since that cost is the transition engine's general bookkeeping (see the RFC's unresolved questions).

## Stores

The row of `component_bench`'s inline table without its button, 10,000 rows, best of two alternating runs:

| Operation | v0.44.0 | Engine v9 |
| --- | ---: | ---: |
| Create, a store | 56.9 ms | 49.1 ms |
| Update every tenth, a store | 2.96 ms | 2.97 ms |
| Create, per-row signals | 31.0 ms | 31.7 ms |
| Update every tenth, per-row signals | 1.18 ms | 1.12 ms |

Store rows mount 14% faster: a field binding's probe ran once per row, read the field, and escaped with an exception before the binding read it again; now only the first row's expression is probed.

## Validation

- **Unit tests:** 3,241 pass on Python 3.14 (one pyright test skips without pyright), with 82% branch coverage, including `tests/test_engine_v9.py` and a zero-mismatch hydration check over `tests/test_ssr_output.py`'s views.
- **Typing and lint:** mypy, ruff, and the formatter pass.
- **Browser tests:** 95 pass in Chromium on Pyodide 314.0.6, including the hydration and full-stack suites, which run the JavaScript kernel's `CLAIM_TPL` walk and correct an attribute value only the browser computes.

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
