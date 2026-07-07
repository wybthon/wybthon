### Performance

#### The big idea

Wybthon component bodies run **once**.  Reactive updates flow through
*reactive holes*: a per-binding effect for each callable child or
prop value.  When a signal changes, only the holes that read it
re-evaluate, and only the affected DOM nodes are touched.  This is
fundamentally cheaper than a full component re-render plus diff, even
though we still use a VDOM internally to batch DOM mutations across
the Python and JS bridge.

#### Template-based mounting

Under Pyodide, mount cost is dominated by Python-to-JS FFI round trips,
not by the DOM operations themselves.  The reconciler therefore
serializes the static parts of each host-element subtree into one HTML
string, parses it through a single `<template>` element, and wires
reactive bindings, event handlers, and dynamic children onto the cloned
nodes in one pass.  Mounting N static nodes costs roughly one FFI call
instead of N.

You get this for free; there's no opt-in.  Subtrees that can't be
expressed as HTML (form-control `value`/`checked`, raw-text elements,
and similar) fall back to node-by-node mounting with identical
behavior.  See the [`template`][wybthon.template] API page.

#### Authoring tips

- **Prefer holes over re-rendering.**  Embed a signal accessor (or
  `dynamic(lambda: ...)`) at the smallest possible spot in the tree
  rather than reading signals eagerly inside the component body.

  ```python
  # Slow: eager reads happen during setup; future changes are missed.
  return p(f"Hello, {name()}, count={count()}")

  # Fast: only two text nodes update.
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
  per-item (or per-index) reactive scopes and **cache the rendered
  subtree per item**: on a list change, only added items map, removed
  items dispose, and reorders move the existing DOM nodes.

- **Use `create_selector` for selection state.**  A selector notifies
  only the previously-selected and newly-selected rows, so selecting a
  row in a 10,000-row table touches two rows instead of all of them.

- **Use `reconcile` for server data.**  Diffing fresh data into a store
  (rather than replacing it) keeps identities stable, so `For` rows for
  unchanged items keep their DOM.

#### Micro-benchmarking

Run the included benchmarks against the stubbed DOM:

```bash
python benchmarks/bench_runner.py
```

The app under test is built the idiomatic fine-grained way (mount once,
then drive everything through signal writes with `For` and
`create_selector`), so the numbers reflect what a well-written Wybthon
app pays. The runner measures:

- Standard JS framework benchmark workloads (create, update, swap, and
  remove rows in a 1k to 10k row table); useful as a regression smoke
  test for the list primitives and the template mount path.
- **`hole update (1k tree)`**: change one signal that drives a single
  reactive hole inside a 1,000-node tree.
- **`full rerender (1k tree)`**: re-render the entire tree and let the
  diffing algorithm reduce the change set to one text node.

Both tree benchmarks update the *same* DOM node; the difference is
entirely in *what work the framework does to figure out the change*.
On the stubbed DOM (which makes every framework cost more visible than
real browser DOM mutations) the gap is dramatic:

| Benchmark              | Mean   |
|------------------------|-------:|
| `hole update (1k tree)` | ~0.01 ms |
| `full rerender (1k tree)` | ~9 ms  |

Fine-grained operations show the same pattern in the table workloads:
selecting a row is ~0.02 ms (two class flips via `create_selector`) and
a partial update of every 10th label is under a millisecond, while
creating 1,000 rows from scratch, which must build and mount 1,000
subtrees, sits in the hundreds of milliseconds.

Use `--bench=<name>` to run a single benchmark or `--json` to emit
machine-readable output.

`benchmarks/browser_bench.py` runs the real browser app (Pyodide +
headless Chromium) for end-to-end numbers that include FFI and layout;
see `benchmarks/README.md`.

## Next steps

- Read [Mental model](../concepts/mental-model.md) for the underlying ideas.
- Browse [Authoring patterns](authoring-patterns.md) for hole-friendly recipes.
- See [Suspense and Lazy Loading](../concepts/suspense-lazy.md) for code-splitting.
