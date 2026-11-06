# Engine v6 evaluation

This evaluation compares [RFC 0006](../../docs/rfcs/0006-engine-v6.md) with v0.40.0 (`11e6cd1`). What changed:

- after a page's first boot, the bootstrap builds a memory snapshot of a runtime with Wybthon imported, and later boots restore it;
- the server writes HTML directly instead of mounting into an in-memory DOM and serializing it;
- `wyb dev` replaces an edited module in place instead of reloading the page.

## Measurement conditions

An Apple M-series laptop (arm64) on macOS, otherwise idle. Native runs used CPython 3.14.5; browser runs used headless Chromium 151 with Pyodide 314.0.6 from the jsDelivr CDN and a warmed HTTP cache.

## Startup

`benchmarks/compare_startup.py` built the starter app from both checkouts and alternated six fresh production boots per checkout in one browser context, after a warmup boot each. The Engine v6 warmup built a snapshot, so its measured boots are repeat visits that restore it (all six did). Medians, in milliseconds:

| Phase | v0.40.0 | Engine v6 |
| --- | ---: | ---: |
| Load and initialize Pyodide | 744.4 | 71.0 |
| Fetch archives (concurrent) | 5.3 | 1.2 |
| Unpack archives | 12.7 | 10.5 |
| Import and initialize the application | 40.7 | 13.1 |
| Ready | 798.8 | 95.5 |
| Next frame after ready | 807.8 | 107.7 |

A repeat visit is ready 8.4 times sooner. Importing the application gets faster too, because the framework it imports is already imported in the snapshot. A first visit boots as before, with one Cache Storage lookup added; when the page is idle afterwards, a worker spent 920 ms building the 31 MB snapshot.

The spike behind the RFC measured the parts separately in the same browser: booting Pyodide normally took 880 to 897 ms, and restoring a snapshot of a runtime that had imported the standard library took 107 to 113 ms. A snapshot made in Node restored and ran in Chromium. With Brotli, a snapshot is 4.1 MB, and a restored runtime still fetches Pyodide's 2.5 MB standard library archive, which is why the bootstrap builds snapshots in the browser rather than shipping them.

## Server rendering

`benchmarks/ssr_bench.py` renders each page with `render_to_string` in CPython. Minimum wall time over seven renders, in milliseconds, from the second of two alternating runs (the first agreed within 2%):

| Page | v0.40.0 | Engine v6 | Ratio |
| --- | ---: | ---: | ---: |
| js-framework-benchmark table, 1,000 rows | 41.33 | 5.77 | 7.16x |
| The same table, 10,000 rows | 468.15 | 59.56 | 7.86x |
| 1,000 `Card` components (props, a `Show`, children) | 61.60 | 15.42 | 3.99x |
| 50 `Errored` and `Loading` boundaries with pending async data | 4.10 | 1.25 | 3.28x |

Every page's HTML was identical between the two checkouts (`--expect` checks it). Rendering a template row now makes about 100 Python calls instead of 535: no VNode tree is built for a template, no kernel commands are emitted, no DOM is built or serialized, and nothing is disposed but owners. A static subtree of a template is serialized once and reused. Components gain less than tables because each still runs its body under a component context, as it must for context and hydration keys.

## Client rendering

`benchmarks/row_bench.py`, two runs per checkout (minimums, milliseconds):

| Operation | v0.40.0 | Engine v6 |
| --- | ---: | ---: |
| Create 1,000 rows | 4.14 to 4.16 | 4.06 to 4.18 |
| Create 10,000 rows | 43.65 to 44.06 | 43.48 to 44.29 |
| Clear 10,000 rows | 14.11 to 14.28 | 13.83 to 13.98 |
| Update every tenth of 10,000 | 1.53 to 1.57 | 1.45 to 1.50 |

Unchanged: the client renderer gained one global read per component mount (the hot update hook, `None` outside `wyb dev`).

## Validation

- **Unit tests:** 1,002 pass on Python 3.14, with 88% branch coverage.
- **Browser tests:** 91 pass in Chromium on Pyodide 314.0.6, including boot snapshots under `wyb preview` and `wyb dev` and a hot update under `wyb dev`.
- **Server output:** before the old renderer was removed, it was kept as an oracle. The unit suite's server renders, 46 renders of the browser fixture app's routes, and a 28-render corpus of markup with serialization rules of its own (now `tests/test_ssr_output.py`) all matched it byte for byte.

## Reproduction

```bash
git worktree add --detach /tmp/wybthon-before 11e6cd1
uv run python benchmarks/ssr_bench.py /tmp/wybthon-before/src --save /tmp/ssr-before.json
uv run python benchmarks/ssr_bench.py src --expect /tmp/ssr-before.json
(cd benchmarks && uv run python compare_startup.py --baseline /tmp/wybthon-before --iterations 6)
uv run python benchmarks/row_bench.py /tmp/wybthon-before/src --reps 7
uv run python benchmarks/row_bench.py src --reps 7
```

The raw reports aren't committed: the tables above are the record of this evaluation.
