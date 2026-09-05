# Runtime performance follow-up

These measurements compare the performance follow-up with the initial PR snapshot, `6bc1d51`, and the original release, `72bc523`. Rendering continues to use a VDOM, integer node handles, native template cloning, and batched JSON commands. The public reactive and store contracts are preserved.

## Method

The browser is Chromium 151.0.7922.34, running Pyodide 314.0.6 on Intel macOS. Comparisons alternate execution order between two isolated checkouts in the same browser, with one warmup and five measured samples per operation. Each ordinary sample restores its own baseline. The tables report median synchronous work through the DOM commit, including JSON serialization and native kernel application, excluding subsequent layout and paint. Negative percentages mean less time.

Machine load varied, so compare the two columns within a table. Don't compare absolute times across tables or against earlier runs. Interleaving reduces drift but doesn't eliminate interference. These are local observations, not portable speed guarantees. The raw reports include individual samples, frame opportunities, runtime metadata, and fingerprints of the Python sources used.

## Signal arrays versus the PR snapshot

| Operation | Before, ms | After, ms | Time change |
| --- | ---: | ---: | ---: |
| Create 1,000 | 113.3 | 90.7 | -19.9% |
| Replace 1,000 | 149.7 | 121.1 | -19.1% |
| Create 10,000 | 963.9 | 779.8 | -19.1% |
| Update every tenth of 10,000 | 12.7 | 9.7 | -23.6% |
| First selection among 10,000 | 0.4 | 1.1 | See selection note |
| Swap two of 10,000 | 51.1 | 19.9 | -61.1% |
| Remove first of 10,000 | 54.5 | 19.3 | -64.6% |
| Append 1,000 to 10,000 | 158.3 | 103.5 | -34.6% |
| Clear 10,000 | 473.8 | 418.8 | -11.6% |

## Transactional stores versus the PR snapshot

| Operation | Before, ms | After, ms | Time change |
| --- | ---: | ---: | ---: |
| Create 1,000 | 130.1 | 108.1 | -16.9% |
| Replace 1,000 | 175.5 | 142.8 | -18.6% |
| Create 10,000 | 1359.6 | 1053.0 | -22.6% |
| Update every tenth of 10,000 | 41.0 | 33.2 | -19.0% |
| First selection among 10,000 | 0.4 | 0.3 | See selection note |
| Swap two of 10,000 | 0.6 | 0.6 | +0.0% |
| Remove first of 10,000 | 38.5 | 36.5 | -5.2% |
| Append 1,000 to 10,000 | 151.6 | 126.0 | -16.9% |
| Clear 10,000 | 457.7 | 428.4 | -6.4% |

## Selection note

The five-sample signal comparison's first-selection median increased from 0.4 to 1.1 ms. Both versions had overlapping samples of approximately 0.2 to 1.2 ms. The difference was in native kernel timing; median Python work decreased from 0.3 to 0.2 ms. A percentage calculated from these small, overlapping samples is unstable.

A separate 31-sample comparison mounts each table once, then toggles selection between two rows with a frame opportunity between samples. Signal mode measured **0.4 -> 0.4 ms**; store mode measured **0.4 -> 0.4 ms**. Each toggle emits two commands. This measures repeated interaction separately from the first selection after a fresh mount.

## Checking the original regressions

This separate comparison uses the original pre-overhaul release as its baseline. It includes improvements from both the initial overhaul and this follow-up, including the selector improvement that was already in the PR.

| Operation | Before, ms | After, ms | Time change |
| --- | ---: | ---: | ---: |
| Create 1,000 | 93.1 | 85.7 | -7.9% |
| Create 10,000 | 815.2 | 767.5 | -5.9% |
| Update every tenth of 10,000 | 11.2 | 9.4 | -16.1% |
| First selection among 10,000 | 4.0 | 0.4 | -90.0% |
| Swap two of 10,000 | 54.8 | 19.8 | -63.9% |
| Append 1,000 to 10,000 | 152.1 | 99.7 | -34.5% |

## Work and memory

- The profiled 10,000-row signal mount fell from 3,550,119 to 2,020,124 Python calls, a 43% reduction. These profiles run separately from the timed samples.
- The delegated store append creates exactly 1,000 rows in one commit, with 7,000 DOM commands, 1,000 recipe hits, and no generic template discovery or full-list scan. `benchmarks/check_work.py` gates this work, plus the existing selection and swap contracts.
- An unobserved 10,000-entity store retained 26.8 MB before and 16.3 MB after, a 39% reduction. This is a separate CPython 3.12.13 tracemalloc measurement; input data and imports are excluded. It measures Python allocations rather than browser memory or process RSS.

## Implementation

- Repeated template shapes use bounded, guarded Python extraction routines. Each instance's tags, child structure, static attributes, and binding kinds are checked before reuse. Changed shapes use generic discovery. Names and values are constants, never interpolated into generated source; callbacks and refs come from the current instance.
- Generic lists retain unchanged prefixes and, when keys are unique, unchanged suffixes. Matching tables cover the remaining middle. Duplicate keys keep occurrence identity. Rows omit an unused item signal, and unobserved integer indices skip propagation work while remaining available to later subscribers.
- Direct signal computations keep their dependency edge and skip unnecessary tracking and async protocol checks. General expressions retain dynamic tracking, cancellation, and transition handling.
- Stores allocate structural signals and mutation journals on demand, preserve staged and held state for late subscribers, skip unneeded subtree propagation, and avoid copying immutable scalar values.
- Native clone registration walks sibling links, and unmounting checks registries before calling cleanup helpers for nodes without registrations.

## Validation and limits

458 unit tests pass on Python 3.12 and 3.14, and all 60 browser tests pass. Ruff, Black, mypy, the strict documentation build, native benchmarks, and browser work gates pass. Branch-inclusive unit coverage is approximately 82%. New tests cover shape changes, per-instance events and refs, cache bounds, duplicate matching, equal keyed replacements, late index subscriptions, and structural subscriptions created during staged or held updates.

Large unvirtualized mounts still allocate a VNode tree and reactive bindings for every row. Arbitrary replacement arrays still need linear identity checks, and removing a row shifts later indices. The improvements reduce that work's overhead; virtualization remains useful when the application doesn't need all rows mounted at once.

See the [raw measurements](runtime-performance.json) and [reproduction instructions](../README.md). CHANGELOG.md remains managed by the release pipeline.
