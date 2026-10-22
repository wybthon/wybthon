# Engine v4 evaluation

This evaluation compares [RFC 0004](../../docs/rfcs/0004-engine-v4.md) with v0.38.0 (`e636b4c`). The virtual DOM, delegated events, and batched JavaScript kernel remain. What changed:

- the compiler: dynamic template expressions are getters, and each literal's parse tree and mount functions are emitted when its module is compiled;
- Solid-style props, read as values;
- the static probe, which applies a binding that reads nothing reactive without allocating a computation;
- bindings as plain computations whose apply stage is a module function, instead of closures;
- list rows that are their own owner, with an index signal created only when it's read;
- one handler per node stored without a per-node dictionary, and VNodes without instance dictionaries;
- keyed matching with identity fast paths for unchanged prefixes and suffixes, and swap detection.

Each side runs its own idiom. The v0.38.0 row is `<tr class={(lambda: "danger" if is_sel(iid) else "")}>...{d["label"]}...`; the Engine v4 row is the same template without the lambda, compiled.

## Measurement conditions

The machine ran unrelated heavy workloads throughout, with load averages from 12 to over 140, so wall-clock times are unreliable and CPU times vary by up to 1.7 times between identical runs. This report leads with **deterministic work measures**: objects the cyclic collector tracks, Python bytes, function calls, and kernel commands. Times are process CPU time; each table cell compares checkouts that ran alternately in fresh processes. Re-run the timed comparisons on an idle machine before quoting them.

## Deterministic work

`benchmarks/row_bench.py` mounts the js-framework-benchmark table natively.

| Work | v0.38.0 | Engine v4 |
| --- | ---: | ---: |
| Objects tracked per mounted row, with selection | 42.0 | 20.0 |
| Objects tracked per mounted row, without selection | 32.0 | 13.0 |
| Bytes retained per row, with selection | 6,082 | 3,856 |
| Bytes retained per row, without selection | 4,514 | 2,352 |
| Function calls, create 1,000 rows with selection | 105,101 | 101,098 |
| Function calls, create 1,000 rows without selection | 91,101 | 84,098 |
| Function calls, create 1,000 store rows (selection, store labels) | 161,285 | 160,284 |
| Kernel commands, create 1,000 rows | 1,000 | 1,000 |
| Kernel commands, swap two of 10,000 | 2 | 2 |

What the rows show:

- **A row keeps half as many objects.** v0.38.0's row kept 10 cells, 8 dictionaries, 7 functions, and 6 tuples, mostly closures for each binding's apply stage and the template's retained values, plus an owner, an index signal, and a row record. An Engine v4 row keeps its two VNodes, two computations, two handler records, the row (which is also its owner), and the dictionaries for the graph's edges; the rest is the application's own click handler.
- **Constant expressions allocate nothing.** `{d["label"]}` makes no calls, so its binding is probed first: the probe finds the signal stored in the dictionary and binds the hole to it directly, without a wrapper computation.
- **Calls fell slightly** even though every dynamic expression is now a compiled getter.

## Template compilation

Compiling a template ahead of time moves its parse, validation, and mount-function generation out of the page. The first use of a template in a page:

| Native CPython, per template | Time |
| --- | ---: |
| Compiled at run time (parse, build, `compile` and `exec` the mount function) | 1,870 µs |
| Precompiled (rebuild the slot plan from constants, install the mount function) | 83 µs |

Pyodide runs Python two to three times slower, so an application with a few hundred templates saves a noticeable share of its startup. The browser test suite checks that a production build never compiles a template at run time: `templates._by_identity` and `templates._by_value` stay empty, and every template the app renders comes from a precompiled entry.

## CPU time, native

Minimum process CPU time per operation (milliseconds), with the median of the per-round ratios across five alternating rounds. Rows use each version's idiomatic selection binding, a projection.

| Operation | v0.38.0 | Engine v4 | Median ratio | Range |
| --- | ---: | ---: | ---: | ---: |
| Create 1,000 | 40.3 | 44.5 | 1.13x | 0.82x to 1.52x |
| Replace 1,000 | 51.0 | 52.8 | 1.12x | 0.88x to 1.67x |
| Create 10,000 | 417.2 | 460.1 | 1.02x | 0.79x to 1.68x |
| Clear 1,000 | 9.0 | 7.7 | 1.23x | 0.90x to 1.92x |
| Clear 10,000 | 84.5 | 73.2 | 1.18x | 0.96x to 2.18x |
| Update every tenth of 10,000 | 5.8 | 5.9 | 1.02x | 0.75x to 1.90x |
| Swap two of 10,000 | 9.9 | 3.7 | 2.65x | 2.07x to 4.58x |
| Remove the first of 10,000 | 7.9 | 4.5 | 2.45x | 1.74x to 3.16x |
| Append 1,000 to 10,000 | 45.1 | 45.9 | 1.09x | 0.86x to 1.27x |

Without the selection binding, which isolates the rendering engines:

| Operation | v0.38.0 | Engine v4 | Median ratio | Range |
| --- | ---: | ---: | ---: | ---: |
| Create 1,000 | 41.5 | 30.1 | 1.11x | 1.03x to 2.20x |
| Replace 1,000 | 50.9 | 35.6 | 1.16x | 1.04x to 2.32x |
| Create 10,000 | 439.6 | 403.0 | 1.09x | 1.07x to 1.67x |
| Clear 1,000 | 7.4 | 5.3 | 1.40x | 1.17x to 1.58x |
| Clear 10,000 | 62.7 | 52.3 | 1.37x | 1.07x to 1.42x |
| Swap two of 10,000 | 11.8 | 4.8 | 2.92x | 2.46x to 3.33x |
| Remove the first of 10,000 | 9.7 | 5.6 | 1.56x | 1.38x to 1.74x |

The minimums and the medians disagree for creating rows with a selection binding, which is what heavy, uneven load does to a minimum: it rewards whichever checkout happened to run during a quiet moment. A tighter comparison, eight pairs of short alternating runs (creating and clearing 1,000 rows, best of nine each), favored Engine v4 in seven pairs, by 1.05 to 1.15 times for creating and 1.15 to 1.25 times for clearing.

### What changed the most

Two decisions moved the timings more than any single optimization:

- **Bindings stay plain `Computation`s.** The first version of this engine made attribute bindings and holes subclasses of `Computation` that kept their state in slots. It allocated as little as the final version, but created rows about 8% *slower* than v0.38.0: CPython 3.14 specializes attribute reads per type, and the reactive core's hottest reads (`_settle`, `_update_if_necessary`, `_run_apply`) saw several types where they had seen one. Keeping every binding a plain `Computation`, with one extra slot (`_apply_data`) for what its apply stage writes to, made creation faster than v0.38.0. RFC 0003 measured the same effect when it moved fields to class defaults.
- **Only call-free expressions are probed.** Probing every compiled getter evaluated reactive expressions twice up to their first read, which doubled the work for an expression like `proj.get(iid)` that does real work before it reads a signal. The compiler records which expressions make no calls, and only those are probed; a store read ends a probe immediately.

## Browser

`benchmarks/compare_browser.py` alternated the checkouts in Chromium with Pyodide 314.0.6, five samples per operation. The load average was between 90 and 147 during these runs, far above the machine's 16 cores, so these are the least reliable numbers here; synchronous commit times, in milliseconds:

| Operation | Signal, v0.38.0 | Signal, Engine v4 | Store, v0.38.0 | Store, Engine v4 |
| --- | ---: | ---: | ---: | ---: |
| Create 1,000 | 154.1 | 137.5 | 128.1 | 199.3 |
| Replace 1,000 | 242.5 | 265.1 | 232.6 | 233.5 |
| Create 10,000 | 2,151.8 | 1,803.6 | 1,947.1 | 2,053.3 |
| Update every tenth of 10,000 | 15.6 | 14.2 | 80.9 | 63.8 |
| Swap two of 10,000 | 57.5 | 20.0 | 0.9 | 3.6 |
| Remove the first of 10,000 | 33.1 | 20.1 | 14.4 | 14.9 |
| Append 1,000 to 10,000 | 105.6 | 103.1 | 273.8 | 143.2 |
| Clear 10,000 | 676.5 | 525.2 | 391.2 | 438.2 |

Signal mode follows the native results: swapping, removing, clearing, and creating 10,000 rows are faster. Store mode's creation numbers moved in opposite directions between 1,000 and 10,000 rows, and its native call count is lower than v0.38.0's, which is consistent with noise; these runs predate the change that ends a probe at the first store read. The browser work gates in `benchmarks/check_work.py` pass: one template clone per appended row, at most two commands per selection and swap, and one per clear.

## Against the RFC's targets

| Target | Result |
| --- | --- |
| At most 20 tracked objects per template row | Met: 20.0 with selection, 13.0 without |
| Creating rows at least 1.3 times faster | Partly met: 1.38x by minimum without selection; about 1.1x by median, and with selection |
| Clearing 10,000 rows at least 1.5 times faster | Missed: 1.18x to 1.37x by median |
| Swapping and removing in 10,000 rows at least 3 times faster natively | Partly met: swap 2.65x to 2.92x by median (up to 4.6x); remove 1.56x to 2.45x |
| Updates no slower | Met |
| No runtime template parsing or code generation in a production build | Met, and checked by the browser tests |

The largest remaining costs per row are the two computations and their edge dictionaries. The next step is the one RFC 0003 also pointed to: cheaper reactive nodes, now that bindings have a single type to optimize for.

## Validation

- **Unit tests:** the full suite passes on Python 3.14, including the typing contracts under mypy and pyright, the compiler's own tests, and the RC.17 additions.
- **Browser tests:** 84 pass in Chromium on Pyodide 314.0.6, with the fixture app built by `wyb build` and its templates compiled.
- **Static checks:** Ruff (lint and format, including the documentation's code blocks), mypy, and the strict documentation build pass.

## Reproduction

```bash
git worktree add --detach /tmp/wybthon-before e636b4c
uv run python benchmarks/row_bench.py src --reps 5 > after.json
uv run python benchmarks/row_bench.py /tmp/wybthon-before/src --reps 5 > before.json
uv run python benchmarks/compare_browser.py --baseline /tmp/wybthon-before > signal-comparison.json
```

Alternate the checkouts across several fresh processes and compare per-round ratios. Raw reports: [native rows](engine-v4-native.json), [browser, signal mode](engine-v4-browser-signal.json), and [browser, store mode](engine-v4-browser-store.json).
