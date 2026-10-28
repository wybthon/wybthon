# Engine v5 evaluation

This evaluation compares [RFC 0005](../../docs/rfcs/0005-engine-v5.md) with v0.39.0 (`7597147`). The virtual DOM, delegated events, the batched JavaScript kernel, and the public API remain. What changed:

- bindings (attributes, text slots, holes, branches) are built, run, and applied in one step;
- a computation keeps its rarely set fields in an extension record, and links to a single source or observer directly;
- a text slot binds its placeholder and becomes a hole only when it holds nodes;
- `For` rows and `Show` and `Switch` regions mount and dispose without closures;
- a compiled template is its entry given a tuple of values, with each slot's binder chosen at compile time;
- disposal breaks every reference cycle the engine creates, the collector's deferred work runs when the browser is idle, and a settled projection costs each reader one subscription;
- the kernel registers only addressed template nodes, never deletes DOM expandos, and empties a parent that a cleared list fills.

## Measurement conditions

An Intel Core i9-9980HK (8 cores, 16 threads) on macOS 15.7, otherwise idle (load average 2 to 4). Native runs used CPython 3.14.8; browser runs used Chromium 151 with Pyodide 314.0.6 (Python 3.14.2). Each comparison alternated the two checkouts: native benchmarks in five rounds of fresh processes, browser operations in seven samples per side after a warmup, in pages of the same browser.

## Deterministic work

`benchmarks/row_bench.py` mounts the js-framework-benchmark table natively.

| Work | v0.39.0 | Engine v5 |
| --- | ---: | ---: |
| Function calls, create 1,000 rows with selection | 101,100 | 61,103 |
| Function calls, create 1,000 rows without selection | 84,100 | 46,103 |
| Objects tracked per mounted row, with selection | 20 | 15 |
| Objects tracked per mounted row, without selection | 13 | 10 |
| Bytes retained per row, with selection | 3,856 | 2,464 |
| Bytes retained per row, without selection | 2,352 | 1,560 |
| Cyclic garbage left by clearing a row | 9 objects | 0 |
| Cyclic garbage left by clearing a `Card` component row | 16 objects | 0 |
| Kernel commands, create 1,000 rows | 1,000 | 1,000 |
| Template nodes registered per benchmark row | 10 | 6 |

What the rows show:

- **A row costs 40% fewer calls.** A binding no longer passes through the general scheduler on its first run, a text slot no longer allocates a hole, and a row no longer runs through per-row lambdas.
- **A row keeps a quarter fewer objects and a third less memory.** It lost four dictionaries (single links replaced the edge sets, and a settled projection no longer adds a readiness subscription per row) and the text slot's hole. What remains is the row, its node, its two bindings, its two handler records, the selection's field subscription, one dictionary for the row's two children, and the application's own handler functions and their cell.
- **Clearing leaves nothing for the cycle collector.** v0.39.0's rows and components referred to their nodes and back, so every clear left its rows as cyclic garbage. `tests/test_engine_v5.py` checks that no framework object survives a clear for the collector to find.

## CPU time, native

Minimum process CPU time per operation (milliseconds), with the median of the per-round ratios across five alternating rounds. Rows use each version's idiomatic selection binding, a projection.

| Operation | v0.39.0 | Engine v5 | Median ratio | Range |
| --- | ---: | ---: | ---: | ---: |
| Create 1,000 | 22.77 | 10.47 | 2.19x | 1.26x to 2.25x |
| Replace 1,000 | 27.91 | 13.72 | 2.01x | 1.30x to 2.46x |
| Create 10,000 | 243.07 | 122.77 | 2.06x | 1.30x to 2.07x |
| Clear 1,000 | 4.66 | 3.03 | 1.71x | 1.53x to 1.79x |
| Clear 10,000 | 56.90 | 36.24 | 1.51x | 1.26x to 1.59x |
| Update every tenth of 10,000 | 4.79 | 3.93 | 1.36x | 1.30x to 1.41x |
| Select a row of 10,000 | 0.16 | 0.15 | 1.24x | 1.06x to 1.29x |
| Swap two of 10,000 | 3.52 | 2.41 | 1.30x | 1.28x to 1.63x |
| Remove the first of 10,000 | 3.80 | 2.73 | 1.23x | 1.16x to 1.40x |
| Append 1,000 to 10,000 | 36.19 | 17.13 | 2.02x | 1.99x to 2.09x |

Without the selection binding, which isolates the rendering engines:

| Operation | v0.39.0 | Engine v5 | Median ratio | Range |
| --- | ---: | ---: | ---: | ---: |
| Create 1,000 | 18.20 | 6.99 | 2.66x | 2.14x to 2.92x |
| Replace 1,000 | 22.40 | 9.29 | 2.31x | 2.10x to 2.55x |
| Create 10,000 | 191.49 | 79.82 | 2.33x | 2.27x to 2.55x |
| Clear 1,000 | 2.80 | 2.01 | 1.45x | 1.34x to 1.49x |
| Clear 10,000 | 28.78 | 22.42 | 1.37x | 1.32x to 1.50x |
| Update every tenth of 10,000 | 4.57 | 3.18 | 1.37x | 1.21x to 1.52x |
| Swap two of 10,000 | 2.90 | 1.95 | 1.48x | 1.35x to 1.69x |
| Remove the first of 10,000 | 3.59 | 2.60 | 1.34x | 1.22x to 1.38x |
| Append 1,000 to 10,000 | 25.84 | 10.30 | 2.40x | 2.35x to 2.72x |

One of the five rounds ran during a burst of unrelated load, which is the low end of each range.

Clearing gains less than creating for a reason that favors Engine v5: a v0.39.0 clear left its rows for the cycle collector, so its time doesn't include freeing them, and a later collection paid for it. An Engine v5 clear frees its rows by reference counting before it returns.

**Components.** Mounting 1,000 `Card` components (a component tag with two props, two text bindings, a signal, a handler, and a `Show`) inside list rows, with dev mode off: 62.8 ms to 31.9 ms (1.97 times faster, by median), and clearing them 14.1 ms to 7.8 ms (1.81 times).

**h() trees.** `benchmarks/bench_runner.py`, whose rows are built with `h()` and mounted into the stub DOM (whose own work dominates), creates 1,000 rows in 61.9 ms instead of 81.3 ms and 10,000 in 641 ms instead of 780 ms, by mean. The Python heap it retains after five create and clear cycles fell from 14.45 MB to 8.32 MB, because cleared rows no longer wait for the collector.

## Browser

`benchmarks/compare_browser.py` invokes each operation directly and splits its synchronous time into Python, serialization, and the JavaScript kernel; "to frame" adds the next animation frame. Medians of seven alternating samples, in milliseconds.

Signal mode:

| Operation | v0.39.0 | Engine v5 | Ratio | Python, v0.39.0 | Python, Engine v5 | Kernel, v0.39.0 | Kernel, Engine v5 | To frame, v0.39.0 | To frame, Engine v5 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Create 1,000 | 58.7 | 33.6 | 1.75x | 51.3 | 26.4 | 6.1 | 6.0 | 64.9 | 45.1 |
| Replace 1,000 | 80.3 | 45.5 | 1.76x | 60.6 | 31.6 | 19.7 | 12.8 | 81.2 | 46.7 |
| Create 10,000 | 536.6 | 263.9 | 2.03x | 464.1 | 196.6 | 64.1 | 55.5 | 691.4 | 264.7 |
| Update every tenth of 10,000 | 9.2 | 8.0 | 1.15x | 6.6 | 5.4 | 1.8 | 1.8 | 10.9 | 9.5 |
| Select a row of 10,000 | 0.5 | 0.5 | 1.00x | 0.3 | 0.3 | 0.2 | 0.0 | 12.3 | 1.9 |
| Swap two of 10,000 | 8.9 | 6.5 | 1.37x | 8.7 | 6.3 | 0.2 | 0.2 | 10.1 | 7.7 |
| Remove the first of 10,000 | 13.6 | 10.6 | 1.28x | 13.4 | 10.5 | 0.2 | 0.1 | 14.9 | 12.2 |
| Append 1,000 to 10,000 | 68.2 | 40.3 | 1.69x | 59.7 | 30.1 | 7.4 | 8.8 | 89.2 | 41.2 |
| Clear 10,000 | 247.6 | 124.0 | 2.00x | 117.9 | 60.3 | 129.7 | 64.2 | 248.4 | 125.4 |

Store mode:

| Operation | v0.39.0 | Engine v5 | Ratio | Python, v0.39.0 | Python, Engine v5 | Kernel, v0.39.0 | Kernel, Engine v5 | To frame, v0.39.0 | To frame, Engine v5 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Create 1,000 | 69.7 | 47.7 | 1.46x | 62.6 | 40.4 | 6.0 | 6.1 | 78.3 | 49.0 |
| Replace 1,000 | 90.1 | 55.9 | 1.61x | 74.4 | 42.1 | 14.7 | 12.8 | 90.7 | 56.7 |
| Create 10,000 | 690.3 | 419.6 | 1.65x | 615.2 | 351.2 | 62.5 | 56.8 | 867.7 | 420.3 |
| Update every tenth of 10,000 | 29.9 | 27.5 | 1.09x | 27.4 | 24.8 | 1.7 | 1.7 | 41.6 | 33.4 |
| Select a row of 10,000 | 0.5 | 0.5 | 1.00x | 0.4 | 0.3 | 0.1 | 0.1 | 8.5 | 2.1 |
| Swap two of 10,000 | 0.6 | 0.6 | 1.00x | 0.5 | 0.5 | 0.1 | 0.1 | 10.5 | 2.2 |
| Remove the first of 10,000 | 7.8 | 6.8 | 1.15x | 7.6 | 6.6 | 0.2 | 0.2 | 12.6 | 8.1 |
| Append 1,000 to 10,000 | 91.5 | 60.1 | 1.52x | 83.1 | 51.1 | 7.0 | 8.7 | 139.5 | 60.9 |
| Clear 10,000 | 229.5 | 145.0 | 1.58x | 131.2 | 82.2 | 97.7 | 62.8 | 231.0 | 145.9 |

What the browser shows beyond the native numbers:

- **Python time halves when creating rows,** as it did natively: 51.3 ms to 26.4 ms for 1,000 rows, and 464 ms to 197 ms for 10,000.
- **Time to the next frame falls further than commit time.** Creating 10,000 rows reached the next frame in 691 ms before and 265 ms after: the collection the mount owed now runs when the page is idle, after the frame.
- **The kernel clears twice as fast:** 130 ms to 64 ms for 10,000 rows, from emptying the list's parent at once and never deleting properties from DOM nodes.
- **Store mode gains less** than signal mode because more of its time is the store's own draft and journal work, which this RFC didn't change.

### The cycle collector

`gc.callbacks` timed the collections inside click-driven operations, and a full collection after `clear(); run_lots()` (10,000 rows mounted after earlier clears):

| Measure | v0.39.0 | Engine v5 |
| --- | ---: | ---: |
| Collections over 10 ms while creating 10,000 rows | 62 to 132 ms, every sample | none |
| Creating 10,000 rows through the button | 568 to 633 ms | 256 to 296 ms |
| Clearing 10,000 rows through the button | 187 to 204 ms | 124 to 128 ms |
| Objects the collector tracks with 10,000 rows mounted | 894,609 | 264,738 |
| One full collection at that point | 1,375 ms | 88 ms |

Most of v0.39.0's tracked objects were garbage from earlier clears, waiting for a full collection that would block the page for more than a second.

## Startup

`benchmarks/compare_startup.py` alternated six fresh production boots of the starter application per checkout, with a warmed HTTP cache. Medians, in milliseconds:

| Phase | v0.39.0 | Engine v5 |
| --- | ---: | ---: |
| Load and initialize Pyodide | 1,412.5 | 1,416.0 |
| Unpack archives | 28.0 | 27.8 |
| Import and initialize the application | 82.5 | 79.0 |
| Ready | 1,534.9 | 1,525.0 |

Startup is unchanged; it's still almost entirely Pyodide's.

## Against the RFC's targets

| Target | Result |
| --- | --- |
| Creating rows at least 2 times faster natively | Met: 2.19x for 1,000 rows and 2.06x for 10,000, by median |
| Creating rows at least 1.8 times faster in the browser | Partly met: 2.03x for 10,000 rows and 1.75x for 1,000 in signal mode; 1.46x to 1.65x in store mode |
| Clearing rows at least 1.8 times faster natively | Missed natively: 1.51x to 1.71x. Met in the browser in signal mode (2.00x), and every clear now frees its rows instead of leaving them for the collector |
| At most 12 tracked objects per row | Missed: 15 with the selection binding (from 20), 10 without (from 13) |
| Mounting the `Card` component at least 2 times faster natively | Nearly met: 1.97x |
| Updates no slower | Met: 1.24x to 1.36x faster natively; 1.00x to 1.37x in the browser |

## Validation

- **Unit tests:** 933 pass on Python 3.14, including 21 new ones in `tests/test_engine_v5.py`; branch coverage is 87%.
- **Browser tests:** 84 pass in Chromium on Pyodide 314.0.6, with the fixture app built by `wyb build`.
- **Static checks:** Ruff (lint and format) and mypy pass.
- **Benchmarks:** `benchmarks/async_bench.py` passes its publication checks, and `benchmarks/bench_runner.py` runs every scenario.

## Reproduction

```bash
git worktree add --detach /tmp/wybthon-before 7597147
uv run python benchmarks/row_bench.py /tmp/wybthon-before/src --reps 7 > before.json
uv run python benchmarks/row_bench.py src --reps 7 > after.json
uv run python benchmarks/compare_browser.py --baseline /tmp/wybthon-before --iterations 7 > signal-comparison.json
uv run python benchmarks/compare_browser.py --baseline /tmp/wybthon-before --iterations 7 --mode store > store-comparison.json
```

Alternate the checkouts across several fresh processes and compare per-round ratios. The raw reports aren't committed: the tables above are the record of this evaluation, and the benchmark workflow uploads fresh reports as artifacts on every run.
