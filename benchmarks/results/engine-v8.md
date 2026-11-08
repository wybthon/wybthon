# Engine v8 evaluation

This evaluation compares [RFC 0009](../../docs/rfcs/0009-engine-v8.md) with v0.43.0 (`374f28f`). What changed in the engine:

- effects reuse one apply scope, re-runs apply at once when no transition can hold them, memo and store reads take one straight-line path, an empty flush returns early, disposal's fast path covers effects, and flushes are scheduled without raising an exception when no event loop runs;
- SVG and MathML templates clone, under any parent;
- hydration doesn't re-send static attributes.

## Measurement conditions

An Apple M-series laptop (arm64) on macOS, CPython 3.14.5. The machine was **heavily loaded by other work** throughout (load averages of 40 to 140 on 8 cores), so every native timing below is the best of several interleaved runs of both checkouts, and the ratios are more trustworthy than the absolute times. Command counts and byte counts are deterministic. No browser timings were taken; the browser suite (95 tests in Chromium on Pyodide 314.0.6) verified behavior.

## The reactive core

A 190-line push-pull reference implementation (staged writes, lazy memos, owners, dynamic dependencies, all plain Python) runs the same operations, to show what each costs without framework layering. Best of three interleaved runs per checkout, microseconds per operation (per tree for the 1,000-effect rows):

| Operation | v0.43.0 | Engine v8 | Speedup | Reference | v0.43.0 / v8 vs. reference |
| --- | ---: | ---: | ---: | ---: | ---: |
| An empty `flush()` | 0.459 | 0.151 | 3.04x | 0.039 | 12.0x / 3.9x |
| Dispose 1,000 render effects | 460 | 270 | 1.70x | 158 | 2.9x / 1.7x |
| Store field read, untracked | 0.158 | 0.098 | 1.60x | 0.040 | 4.0x / 2.5x |
| Store field write and flush, one observer | 4.86 | 3.46 | 1.40x | 1.72 | 2.6x / 2.0x |
| Write and flush, one render effect | 2.21 | 1.68 | 1.32x | 0.63 | 3.4x / 2.7x |
| Write and flush, 100 user effects | 104 | 79 | 1.31x | 41 | 2.5x / 1.9x |
| Write and flush, a memo read by 100 render effects | 115 | 89 | 1.30x | 41 | 2.8x / 2.1x |
| Write and flush, one user effect | 2.25 | 1.73 | 1.30x | 1.09 | 2.1x / 1.6x |
| Write and flush, a memo read by one render effect | 3.26 | 2.67 | 1.22x | 1.09 | 2.9x / 2.4x |
| Create and dispose 1,000 render effects | 2,075 | 1,796 | 1.16x | 612 | 3.4x / 2.9x |
| Update every tenth of 1,000 store rows | 343 | 303 | 1.13x | 124 | 2.8x / 2.4x |
| Store row field read, tracked | 1.05 | 0.93 | 1.13x | 0.20 | 5.3x / 4.7x |
| Create a render effect | 1.97 | 1.76 | 1.12x | 0.62 | 3.2x / 2.8x |
| Write and flush, a chain of 100 memos | 72 | 69 | 1.05x | 47 | 1.5x / 1.5x |
| Create an effect and flush | 2.21 | 2.11 | 1.05x | 0.62 | 3.6x / 3.4x |
| A template binding (the `_bind` fast path) | 0.845 | 0.856 | 0.99x | 0.622 | 1.4x / 1.4x |
| Create a memo | 1.35 | 1.39 | 0.98x | 0.62 | 2.2x / 2.2x |
| Create a signal | 0.216 | 0.217 | 1.00x | 0.052 | 4.2x / 4.2x |

Updates, flushes, disposal, and stores are 1.1 to 3 times faster. Creating computations barely moved: that cost is the transition machinery every computation carries, which this RFC restructured around rather than removed (see the RFC's unresolved questions). A tracked store row read is two field reads (`store[i]["n"]`) and two field subscriptions created and released per read in this benchmark, against one signal read.

## Rows

`benchmarks/row_bench.py`, three interleaved runs per checkout, best time in milliseconds:

| Operation | v0.43.0 | Engine v8 |
| --- | ---: | ---: |
| Create 1,000 rows | 6.31 | 6.60 |
| Create 10,000 rows | 72.3 | 74.8 |
| Clear 10,000 rows | 22.4 | 27.0 |
| Update every tenth of 10,000 | 2.58 | 2.35 |
| Swap two of 10,000 | 1.54 | 1.43 |
| Append 1,000 to 10,000 | 7.67 | 8.14 |

Unchanged within this machine's noise: a second run of Engine v8 alone created 1,000 rows in 4.28 ms. Creating 1,000 rows makes 61,098 Python calls (61,103 before), keeps 2,464 bytes per row, and 15.0 objects per row for the cycle collector, as before.

## SVG

The benchmark row with an inline SVG icon (`<svg width="16" height="16" viewBox="0 0 16 16"><path d="M4 4L12 12M12 4L4 12"></path></svg>`) in place of its `<span>` icon, creating 1,000 rows:

| | v0.43.0 | Engine v8 |
| --- | ---: | ---: |
| Time | 28.4 ms | 4.9 ms (5.8x) |
| Commands' JSON | 837 KB | 54 KB |
| Same row without the icon | 4.4 to 4.9 ms | 4.9 ms |

An SVG icon now costs what any other markup costs.

## Hydration

Hydrating 1,000 server-rendered benchmark rows with the Python backend, with no mismatches:

| | v0.43.0 | Engine v8 |
| --- | ---: | ---: |
| Commands | 19,007 | 13,007 |
| JSON | 569 KB | 357 KB |

The 6,000 commands that are gone set static attributes the server had already written. A client render of the same rows sends 1,008 commands.

## Validation

- **Unit tests:** 1,175 pass on Python 3.14 (one pyright test skips without pyright), plus 1,763 checks that every `wybthon` import in the documentation's code blocks and every API cross-reference resolves.
- **Typing:** the fixtures check with mypy and pyright, with no plugin.
- **Browser tests:** 95 pass in Chromium on Pyodide 314.0.6, including SVG templates cloned under an SVG parent, native `on:click` listeners, and the full-stack suite.

## Reproduction

```bash
git worktree add --detach /tmp/wybthon-before 374f28f
uv run python benchmarks/row_bench.py /tmp/wybthon-before/src --reps 5
uv run python benchmarks/row_bench.py src --reps 5
uv run python benchmarks/core_bench.py --repo /tmp/wybthon-before
uv run python benchmarks/core_bench.py
```

The comparison against the reference implementation used a scratch script that isn't committed; the tables above are the record of this evaluation.
