# Engine v7 evaluation

This evaluation compares [RFC 0007](../../docs/rfcs/0007-engine-v7.md) with v0.41.0 (`cfa9e2b`). What changed:

- stores wrap their containers lazily, when they're first read;
- each container is a copy-on-write signal of its own data, replacing the persistent vector;
- dataclass stores, typed as the dataclass, and dict stores read with subscripts;
- shallow stores.

## Measurement conditions

An Apple M-series laptop (arm64) on macOS, otherwise idle. Native runs used CPython 3.14.5; browser runs used headless Chromium 151 with Pyodide 314.0.6.

## Browser: store mode

`benchmarks/compare_browser.py --mode store --iterations 5` built the benchmark app from both checkouts and alternated the operations in two pages of one browser. Median synchronous commit time, in milliseconds, with its Python and kernel parts:

| Operation | v0.41.0 | Engine v7 | Change | Python, v0.41.0 to v7 | Kernel, v0.41.0 to v7 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Create 1,000 rows | 18.8 | 15.6 | -17% | 15.9 to 12.7 | 2.3 to 2.5 |
| Replace 1,000 rows | 24.0 | 21.9 | -9% | 18.3 to 16.0 | 5.3 to 5.4 |
| Create 10,000 rows | 193.3 | 150.5 | -22% | 163.7 to 120.0 | 23.9 to 23.0 |
| Update every tenth row | 10.9 | 7.4 | -32% | 9.4 to 6.1 | 1.1 to 1.1 |
| Select a row | 0.3 | 0.2 | | 0.2 to 0.2 | 0.1 to 0.1 |
| Swap two rows | 0.4 | 0.6 | +0.2 ms | 0.2 to 0.5 | 0.1 to 0.1 |
| Remove a row | 3.2 | 2.6 | -19% | 3.2 to 2.5 | 0.1 to 0.1 |
| Append 1,000 rows | 21.0 | 16.9 | -20% | 17.2 to 13.3 | 3.4 to 3.3 |
| Clear 10,000 rows | 75.2 | 75.0 | 0% | 45.0 to 47.7 | 29.9 to 27.3 |

The savings are all Python time, and they come from creating rows (no node, `Signal`, or state record is built for a container until it's read, and none for its fields until they're read in a tracking scope) and from writing them (one copy of each edited row, and its fields published with the row's own commit). Swapping copies the 10,000-row list once, where the persistent vector edited two paths of its tree. Clearing is per-row disposal, which this work doesn't change.

## Browser: signal mode

`benchmarks/compare_browser.py --mode signal --iterations 5`, same conditions:

| Operation | v0.41.0 | Engine v7 |
| --- | ---: | ---: |
| Create 1,000 rows | 12.6 | 12.4 |
| Replace 1,000 rows | 17.9 | 17.6 |
| Create 10,000 rows | 120.8 | 120.4 |
| Update every tenth row | 3.8 | 3.9 |
| Select a row | 0.2 | 0.3 |
| Swap two rows | 3.6 | 3.5 |
| Remove a row | 5.0 | 5.0 |
| Append 1,000 rows | 16.9 | 14.7 |
| Clear 10,000 rows | 56.5 | 57.8 |

Unchanged within noise: signal mode uses a store only for its selection projection.

## Store mode against signal mode

Signal mode keeps a hand-made label signal in each row, which applications don't write; store mode is the idiomatic program. In v0.41.0, store mode took 60% longer to create 10,000 rows and 2.9 times as long to update every tenth row. In Engine v7 it takes 25% longer to create them and 1.9 times as long to update them, and it's still much faster to swap (0.6 against 3.5 ms) and remove (2.6 against 5.0 ms) rows, because it edits the list in place instead of replacing it. The RFC's targets (within 10% on create and update) aren't met; see its results section.

## Native

`benchmarks/core_bench.py`, two alternating runs per checkout, nine iterations each after two warmups (median process CPU time, milliseconds):

| Workload | v0.41.0 | Engine v7 |
| --- | ---: | ---: |
| Create a 10,000-row store | 15.56 to 15.84 | 0.01 |
| Create 10,000 rows and subscribe to a field of each | 48.94 to 49.41 | 34.46 to 37.35 |
| Write 1,000 fields and flush | 4.53 to 4.66 | 3.23 to 3.55 |
| Clear a 10,000-row store with a draft | 2.48 to 2.51 | 2.70 to 2.79 |
| Baseline: write 1,000 signals and flush | 1.13 to 1.19 | 1.17 to 1.22 |
| Baseline: 10,000 rows with a signal each, subscribed | 80.92 to 82.08 | 82.38 to 89.22 |

A store field write went from about 3.9 to about 2.8 times a signal write. Most of what remains is the setter's draft views (one per container it reaches) and its copy of each edited container; the subscribed effect also reads two store fields (`store[i]["n"]`) where the signal baseline reads one signal.

Retained memory for a 10,000-row store, measured with `tracemalloc`:

| | v0.41.0 | Engine v7 |
| --- | ---: | ---: |
| After creating it | 5.78 MB | 496 bytes |
| After reading every row | 6.26 MB | 4.48 MB |

## Clearing large lists

A Chromium spike measured the kernel's share of clearing 10,000 benchmark rows. Walking the removed rows' DOM to release their ids took 5 to 7 ms, the same as iterating the ids directly (both are mostly `Map` deletions), and removing the rows took about 12 ms of native DOM work. Releasing by id range wouldn't help, so the kernel is unchanged.

## Validation

- **Unit tests:** 1,013 pass on Python 3.14, including the store, transition, and concurrency contract suites unchanged in what they assert, and new tests for dataclass stores, shallow stores, and lazy wrapping.
- **Typing:** the typing fixtures check dataclass and `TypedDict` stores with mypy and pyright, with no plugin.

## Reproduction

```bash
git worktree add --detach /tmp/wybthon-before cfa9e2b
uv run python benchmarks/compare_browser.py --baseline /tmp/wybthon-before --mode store
uv run python benchmarks/compare_browser.py --baseline /tmp/wybthon-before --mode signal
uv run python benchmarks/core_bench.py --repo /tmp/wybthon-before
uv run python benchmarks/core_bench.py
```

`core_bench.py` reads stores with subscripts, which both checkouts support, so the same script measures either one. The raw reports aren't committed: the tables above are the record of this evaluation.
