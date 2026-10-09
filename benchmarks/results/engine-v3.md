# Engine v3 evaluation

This evaluation compares [RFC 0003](../../docs/rfcs/0003-engine-v3.md) with v0.37.0 (`1c3c312`). The virtual DOM, delegated events, and batched JavaScript kernel remain. What changed:

- markup written as compiled t-string templates (`html(t"...")`);
- what a component costs: constant props, inert bindings, and native control-flow regions;
- one props system;
- placeholder-free component children in helper shapes.

## Measurement conditions

The machine ran unrelated heavy workloads throughout this evaluation, including a virtual machine, video encoding, and another project's browser benchmarks. The load average ranged from 16 to over 600, so wall-clock times were meaningless. This report therefore leads with **deterministic work measures**: function calls, kernel commands, reactive nodes created, and Python bytes retained. These don't depend on load.

Times are **process CPU time**, taken as the minimum over many repetitions, with the two checkouts alternating in fresh processes. CPU time still inflates under contention, so compare the two columns within a row, not absolute values. Re-run the timed comparisons on an idle machine before quoting them.

## Deterministic work

`benchmarks/row_bench.py` mounts the js-framework-benchmark table, and the dashboard is the profiling dashboard: 237 component instances in v0.37.0, with typed props, `Show`, `Switch`, a context provider, and t-string holes.

| Work | v0.37.0 | Engine v3 |
| --- | ---: | ---: |
| Function calls, create 1,000 rows (element helpers) | 112,094 | 109,091 |
| Function calls, create 1,000 rows (template rows) | n/a | 63,091 |
| Kernel commands, create 1,000 rows (either style) | 1,000 | 1,000 |
| Function calls, mount 100 components with 3 constant props | 16,401 | 10,999 |
| Signals and computations, same 100 components | 300 and 300 | 0 and 0 |
| Function calls, mount 100 `Show` regions | 14,201 | 8,199 |
| Signals and computations, same 100 `Show` regions | 100 and 200 | 0 and 100 |
| Function calls, mount 100 raw holes (reference) | 5,303 | 5,401 |
| Dashboard mount: signals created | 407 | 1 |
| Dashboard mount: computations created | 554 | 350 |
| Dashboard mount: kernel commands | 799 | 692 |
| Bytes retained per row (helpers, no selection) | 5,379 | 4,131 |
| Bytes retained per row (templates, no selection) | 5,379 | 4,554 |
| Bytes retained per row (templates, with selection) | 5,955 | 6,122 |

What the rows show:

- **Template rows** run 44% fewer function calls than helper rows. They build no VNode tree for static markup and check no shape guards.
- **Constant props** cost nothing. A component mounted in another component's output, a row, or a branch can never be patched, so its constant props create no signal and no binding.
- **`Show` costs about 1.5 times a raw hole.** Before, it cost 2.7 times, because it built a component, a props mapping, a truthiness memo, and two owners.
- **Template rows with a selection binding** retain slightly more memory per row than sealed helper rows (6,122 against 5,955 bytes). A template instance keeps its values tuple and slot records so a re-rendering hole can patch it, where a sealed helper row keeps nothing.

## CPU time

### Rows

Minimum process CPU time per operation, over 6 alternating rounds of 9 repetitions. Each speedup compares that row's two columns.

| Operation | v0.37.0 helpers | v3 helpers | v3 templates |
| --- | ---: | ---: | ---: |
| Create 1,000 | 49.1 ms | 47.5 ms (1.03x) | 39.3 ms (1.25x) |
| Replace 1,000 | 59.6 ms | 53.9 ms (1.11x) | 45.6 ms (1.31x) |
| Create 10,000 | 505.5 ms | 523.5 ms (0.97x) | 428.5 ms (1.18x) |
| Append 1,000 to 10,000 | 53.5 ms | 62.5 ms (0.86x) | 45.3 ms (1.18x) |
| Clear 1,000 | 7.1 ms | 5.6 ms (1.27x) | 6.4 ms (1.11x) |
| Clear 10,000 | 65.1 ms | 52.3 ms (1.25x) | 59.3 ms (1.10x) |
| Update every tenth of 10,000 | 6.9 ms | 6.7 ms | 6.8 ms |
| Swap two of 10,000 | 11.8 ms | 11.7 ms | 11.9 ms |
| Remove first of 10,000 | 9.0 ms | 9.6 ms | 9.8 ms |

That table has no selection binding, which isolates the rendering engines. With each version's idiomatic selection binding, template rows created 1,000 rows in 45.3 ms against 63.2 ms (1.39x), and 10,000 in 474.6 ms against 658.4 ms (1.39x).

Update, swap, and remove are within the noise in every configuration.

### Dashboard

The dashboard is written with element helpers in both checkouts. Minimum process CPU time over 3 alternating rounds:

| Operation | v0.37.0 | Engine v3 |
| --- | ---: | ---: |
| Mount | 26.6 ms | 21.5 ms (1.24x) |
| Unmount | 2.7 ms | 2.1 ms (1.27x) |
| `Show` open (8 rows) | 1.00 ms | 0.88 ms (1.13x) |
| `Show` close | 0.29 ms | 0.24 ms (1.21x) |
| Stat update (3 holes) | 0.14 ms | 0.13 ms |
| Theme toggle (13 bindings) | 0.17 ms | 0.17 ms |

## Against the RFC's targets

| Target | Result |
| --- | --- |
| Template rows at least 1.8 times faster to create | Missed: 1.25 to 1.39 times by CPU time, with 44% fewer calls |
| Component trees at least 2 times faster to mount | Missed: 1.24 times for the helper-written dashboard; components with constant props run a third fewer calls and allocate no reactive nodes |
| `Show` within 1.5 times a raw hole | Met, by call count |
| Lower retained memory per binding | Met for helpers (23% less per row); template rows with selection retain 3% more |
| Updates no slower | Met |

The largest remaining costs in creating a row are the same with either authoring style:

- the row's owner and its index signal;
- the label's render computation;
- the two delegated handler records.

Each is one object, so further gains need cheaper reactive nodes rather than less tree work.

## Reverted: moving rare fields out of computations

Moving rarely set `Computation` and `Owner` fields to class defaults cut a computation from 328 to 216 bytes. But reads of those fields on these instances weren't specialized by CPython 3.14 and were 3.5 times slower than slot reads (measured on the real classes), and every apply, settle, and disposal reads several of them. Helper row creation was about 15% slower with the change, so it was reverted.

## Validation

- **Unit tests:** 785 pass on Python 3.14 with 87% branch coverage. That includes 46 template tests, 15 zero-cost component tests, and typing contracts for `For`, `Show`, and `html` under both mypy and pyright.
- **Browser tests:** 79 pass in Chromium on Pyodide 314.0.6. Eight of them cover templates in the real HTML parser: compiled rows inside a `<tbody>`, slot patching, component tags, event spellings, whitespace, and SVG expansion.
- **Static checks:** Ruff, mypy, and the strict documentation build pass.

## Reproduction

```bash
git worktree add --detach /tmp/wybthon-before 1c3c312
uv run python /tmp/wybthon-before/benchmarks/row_bench.py /tmp/wybthon-before/src --reps 9 --noselect > before.json
uv run python benchmarks/row_bench.py src --reps 9 --noselect > helpers.json
uv run python benchmarks/row_bench.py src --reps 9 --noselect --template > templates.json
```

Alternate the checkouts across several fresh processes and compare minimums. Raw reports: [native rows and dashboard](engine-v3-native.json).
