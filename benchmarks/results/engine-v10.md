# Engine v10 evaluation

This evaluation compares [RFC 0011](../../docs/rfcs/0011-engine-v10.md) with v0.45.0 (`ea7d700`). Engine v10 changes how components are written (parameters are props) and when flow-control content is built (lazily, when a branch shows). It doesn't change the renderer, so the question is whether the new form costs anything, and what lazy branches save.

## Measurement conditions

An Apple M-series laptop (arm64) on macOS, CPython 3.14.5, alternating the two checkouts in fresh processes, best times shown. The benchmark scripts write each component in its checkout's own idiom: a `ParentProps` class on v0.45.0, parameters on Engine v10. Command and call counts are deterministic.

## Components and control flow

`benchmarks/component_bench.py`, two rounds of seven repetitions:

| Row | Create, v0.45.0 | Create, Engine v10 | Calls per row | Commands per row | Bytes per row |
| --- | ---: | ---: | ---: | ---: | ---: |
| Inline markup | 2.83 ms | 2.82 ms | 35 → 35 | 1 → 1 | 986 → 986 |
| Inline markup with a `Show` | 5.29 ms | 5.20 ms | 71 → 69 | 1 → 1 | 2,826 → 2,834 |
| The markup in a component | 5.89 ms | 5.93 ms | 84 → 83 | 2 → 2 | 3,002 → 2,962 |
| A component with a `Show` | 8.67 ms | 8.51 ms | 120 → 117 | 2 → 2 | 4,842 → 4,810 |

A component written with parameters costs what one written with a props class did, and a little less: its props class has no `key` field and no class-level dataclass machinery. A closed `Show` no longer builds its content's template node, which saves two calls per row.

Hydrating the inline and component tables is unchanged: 1.01 and 3.01 commands per row, no mismatches, 19.3 to 19.5 ms and 28.6 ms.

## Hidden branches

A scratch measurement (not committed): 1,000 list rows, each with a `Show` whose closed branch holds markup and a component with four bindings, and whose fallback is a short template. Best of nine:

| Operation | v0.45.0 | Engine v10 |
| --- | ---: | ---: |
| Create 1,000 rows, branches closed | 6.29 ms | 5.64 ms |
| Open all 1,000 branches | 8.21 ms | 7.51 ms |

Creating the rows is 10% faster because the closed branches' content is never built. Opening them is 9% faster too: building the content fresh costs less than copying the node tree the old branch held, which it copied so a reopened branch could mount again.

## Rows and server rendering

`benchmarks/row_bench.py` (the js-framework-benchmark table, which has no components or flow controls), best of two runs:

| Operation | v0.45.0 | Engine v10 |
| --- | ---: | ---: |
| Create 1,000 rows | 4.14 ms | 4.21 ms |
| Create 10,000 rows | 44.79 ms | 44.04 ms |
| Clear 10,000 rows | 14.31 ms | 14.27 ms |
| Update every tenth of 10,000 | 1.28 ms | 1.24 ms |
| Swap two of 10,000 | 0.83 ms | 0.85 ms |
| Append 1,000 to 10,000 | 5.00 ms | 4.90 ms |

Creating 1,000 rows makes 61,094 Python calls on both, and a row keeps 2,464 bytes. The differences are noise.

`benchmarks/ssr_bench.py` renders the same HTML on both checkouts (`--expect` matches every page). The 1,000 cards page, whose `Card` has a `Show` with a fallback, rendered in 15.38 ms against 15.97 ms; the tables were unchanged (5.16 ms and 53.67 ms against 5.17 ms and 53.47 ms).

## Validation

- **Unit tests:** 3,240 pass on Python 3.14, with 82% branch coverage, including `tests/test_engine_v10.py`.
- **Browser tests:** 95 pass in Chromium on Pyodide, including the hydration, full-stack, and production-build suites.
- **Typing and lint:** mypy, ruff, and the formatter pass; the typing fixtures pass under mypy and pyright.

## Reproduction

```bash
git worktree add --detach /tmp/wybthon-before ea7d700
uv run python benchmarks/component_bench.py /tmp/wybthon-before/src --reps 7
uv run python benchmarks/component_bench.py src --reps 7
uv run python benchmarks/row_bench.py /tmp/wybthon-before/src --reps 5
uv run python benchmarks/row_bench.py src --reps 5
uv run python benchmarks/ssr_bench.py /tmp/wybthon-before/src --save ssr-before.json
uv run python benchmarks/ssr_bench.py src --expect ssr-before.json
```
