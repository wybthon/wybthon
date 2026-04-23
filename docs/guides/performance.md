### Performance

#### The big idea

Wybthon component bodies run **once**.  Reactive updates flow through
*reactive holes* — a per-binding effect for each callable child or
prop value.  When a signal changes, only the holes that read it
re-evaluate, and only the affected DOM nodes are touched.  This is
fundamentally cheaper than a full component re-render + diff, even
though we still use a VDOM internally to batch DOM mutations across
the Python ↔ JS bridge.

#### Authoring tips

- **Prefer holes over re-rendering.**  Embed a signal accessor (or
  `dynamic(lambda: ...)`) at the smallest possible spot in the tree
  rather than reading signals eagerly inside the component body.

  ```python
  # Slow — eager reads happen during setup; future changes are missed.
  return p(f"Hello, {name()}, count={count()}")

  # Fast — only two text nodes update.
  return p("Hello, ", span(name), ", count=", span(count))
  ```

- **Co-locate signals with the smallest visible region.**  A hole is
  cheaper than a `Show`/`For` re-evaluation, and a `For`/`Index`
  per-item scope is cheaper than a `dynamic` returning the full list.

- **Use `create_memo` for derived values.**  Memoised getters work
  out-of-the-box as reactive holes: `span(my_memo)`.

- **Use `key` on lists.**  Keyed reconciliation reorders existing
  DOM nodes in place instead of re-creating them.  Prefer stable IDs
  over indices for keys.

- **Batch updates with `batch()`.**  When a single user action
  triggers multiple `set()` calls, wrap them in `batch()` so all
  affected holes flush together.

- **Use `For` / `Index` for dynamic lists.**  These maintain stable
  per-item (or per-index) reactive scopes so the mapping callback
  runs once per unique item, not per re-render.

#### Micro-benchmarking

Run the included benchmarks against the stubbed DOM:

```bash
python benchmarks/bench_runner.py
```

The runner measures:

- Standard JS framework benchmark workloads (create / update / swap /
  remove rows in a 1k–10k row table) — useful as a regression smoke
  test for the diffing algorithm.
- **`hole update (1k tree)`** — change one signal that drives a single
  reactive hole inside a 1,000-node tree.
- **`full rerender (1k tree)`** — re-render the entire tree and let the
  diffing algorithm reduce the change set to one text node.

Both tree benchmarks update the *same* DOM node; the difference is
entirely in *what work the framework does to figure out the change*.
On the stubbed DOM (which makes every framework cost more visible than
real browser DOM mutations) the gap is dramatic:

| Benchmark              | Mean   |
|------------------------|-------:|
| `hole update (1k tree)` | ~0.01 ms |
| `full rerender (1k tree)` | ~25 ms  |

In real Pyodide deployments the absolute numbers shift, but the
relative ordering is the same: skipping the diff entirely is always a
win.

Use `--bench=<name>` to run a single benchmark or `--json` to emit
machine-readable output.
