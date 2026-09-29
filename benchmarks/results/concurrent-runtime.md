# Concurrent reactive runtime validation

This change replaces the single shared transition with dependency-linked publication groups. It retains the Virtual DOM, template recipes, persistent store sequences, edit journals, delegated events, and batched JavaScript kernel.

## Correctness

Validation on Python 3.12 and Pyodide 314.0.6 in Chromium 151:

- 527 native tests pass, with 83% combined statement and branch coverage.
- 62 browser tests pass.
- Ruff, Black, mypy, and the strict MkDocs build pass.
- The new concurrency suite covers independent and shared requests, latest and pending read modes, quiet refreshes through arbitrary expressions, streams, cancellation, optimistic rebasing and acknowledgment, subtree pending indicators, provisional resources, speculative errors, lifecycle callbacks, and unmount cleanup.
- The typed component fixture is checked by mypy and executed in the renderer.

The executable behavioral contract is described in [Runtime contracts](../../docs/concepts/runtime-contracts.md). Intentional breaking changes include independent action publication, accessor-only component annotations, ordinary `Props.get` defaults, defaults in Props iteration, and `until` returning the settled truthy result.

## Synchronous browser comparison

Baseline: `0c9752b29fca52b82617a199c65329f9c173ea75`. The comparison uses an isolated baseline checkout, identical store workloads, one warmup, five measured samples per side, and alternating execution order. Each sample restores its starting list. The changed source digest matches the final tested Python source. Source digests and raw samples are included in [the comparison report](concurrent-runtime-browser.json).

The measurements include Python work, serialization, and kernel application. Frame measurements are rendering opportunities, not proof of completed paint. Machine load, garbage collection, and browser scheduling affect durations; these are local measurements, not cross-framework rankings.

| Operation | Baseline median | Changed median | Change |
| --- | ---: | ---: | ---: |
| Mount 10,000 rows | 1,244.4 ms | 1,287.9 ms | +3.5% |
| Update every tenth row | 30.9 ms | 32.1 ms | +3.9% |
| Append 1,000 to 10,000 rows | 158.6 ms | 156.2 ms | -1.5% |

The ordinary binding path caches its provisional owner link and avoids allocating a preparation owner when a computation creates no owned resources. This avoids walking the ownership tree for every ordinary binding. Some synchronous overhead remains from the stronger ownership and publication contract. This is a correctness and concurrency improvement, not a synchronous rendering speedup.

Both comparison checkouts emitted one commit with 70,000 DOM operations for a 10,000-row mount, 1,000 operations for the partial update, and 7,000 operations for the append. Separate deterministic work-count gates cover row creation, list scanning, template recipes, selection, swapping, and batching.

## Async publication

Run:

```sh
python benchmarks/async_bench.py --widths 10 100 1000
```

The benchmark starts independent gated requests under split effects, releases one request, and then releases the rest. It asserts visible values at each step and verifies that no tasks, held nodes, or held applications remain after disposal. CI runs the same assertions and uploads the report.

In the [native report](concurrent-runtime-async.json), starting N requests performs 2N computations and creates N groups. Releasing one performs one computation and publishes one group while the others remain held. Releasing the rest performs N-1 computations and publishes N-1 groups. These counts hold at widths of 10, 100, and 1,000.

At width 1,000, this run measured about 55 ms to start the work, 12 ms to publish the first result, and 23 ms to publish the remainder. Timing includes the benchmark's explicit settle ticks. Group readiness bookkeeping still scales with the number of open groups, even though only one consumer recomputes when one request completes. This native benchmark excludes the DOM and network.

## Follow-up performance priorities

Reduce per-binding and per-row allocation costs, make ready-group checking more selective at large concurrency widths, and measure production startup separately. Keep the existing deterministic collection gates while doing so. The retained VDOM and kernel already batch mutations effectively; these measurements don't motivate replacing them.
