# Wybthon Benchmarks

Performance benchmarks modelled on the
[js-framework-benchmark](https://github.com/krausest/js-framework-benchmark)
suite by Stefan Krause.  The same nine operations and data-generation
approach are used so results are directly comparable.

## Benchmarked operations

| # | Name | Description | Warmup |
|---|------|-------------|--------|
| 1 | create rows | Create 1,000 rows from scratch | 5 |
| 2 | replace all rows | Replace all 1,000 rows with new data | 5 |
| 3 | partial update | Update every 10th row's label | 3 |
| 4 | select row | Highlight one row via CSS class | 5 |
| 5 | swap rows | Swap rows at index 1 and 998 | 5 |
| 6 | remove row | Remove one row from the middle | 5 |
| 7 | create many rows | Create 10,000 rows from scratch | 5 |
| 8 | append rows | Append 1,000 rows to a 10,000-row table | 5 |
| 9 | clear rows | Clear all rows | 5 |

### Reactive-hole microbenchmarks

These two benchmarks are run after the standard nine to highlight the
benefit of the fully-reactive component model.  Both mount a `<div>` of
1,000 `<span>` children and then update one text node per iteration:

| # | Name | Description | Warmup |
|---|------|-------------|--------|
| 10 | hole update (1k tree) | Single signal write inside `batch(...)` updates one reactive hole — the reconciler is **not** re-invoked | 5 |
| 11 | full rerender (1k tree) | The whole tree is re-built and the reconciler diffs its way to the same single text update | 5 |

The "hole update" path is typically several orders of magnitude faster
than the "full rerender" path on the stubbed DOM, which is the whole
point of fine-grained reactivity.

Memory measurements (optional):
- **ready** — baseline after page/module load
- **run 1k** — after creating 1,000 rows
- **create/clear 5×** — after 5 cycles of create-then-clear 1,000 rows

---

## Quick start — stubbed-DOM benchmark

Runs all nine operations against a lightweight DOM stub.
No browser or Pyodide required.

```bash
# From the repository root
pip install -e .
python benchmarks/bench_runner.py
```

Options:

```
--json             Output as JSON
--memory           Include memory measurements (tracemalloc)
--warmup N         Override warmup iterations (default: per-benchmark)
--iterations N     Measured iterations (default: 10)
```

---

## Browser benchmark app

A full interactive implementation that runs in a real browser via Pyodide.
This is the version that could be submitted to
`krausest/js-framework-benchmark`.

### Running locally

```bash
# Serve the project root
python -m http.server 8000

# Open in browser
open http://localhost:8000/benchmarks/app/index.html
```

The page loads Pyodide from CDN, copies the Wybthon source into Pyodide's
virtual filesystem, and runs `main.py`.

### Submitting to js-framework-benchmark

To add Wybthon to the official benchmark:

1. Fork [krausest/js-framework-benchmark](https://github.com/krausest/js-framework-benchmark)
2. Create `frameworks/keyed/wybthon/`
3. Copy `benchmarks/app/index.html` and `benchmarks/app/main.py`
4. Add a `package.json` with a serve script
5. Bundle or reference the Wybthon source (Pyodide loads it at runtime)
6. Follow the repo's contribution guide to open a PR

---

## CI integration

The `.github/workflows/bench.yml` workflow runs the stubbed-DOM
benchmark on every push and PR, printing a results table in the Actions
log.  This makes it easy to spot performance regressions.
