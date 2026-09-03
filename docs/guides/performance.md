# Performance

## The big idea

Wybthon component bodies run **once**. Reactive updates flow through *holes*: a render effect per reactive expression in the tree, and a binding per reactive prop value. When a signal changes, only the holes that read it re-evaluate, and only their DOM nodes are touched. The unit of update is the hole, not the component, so there is no component re-render to optimize away.

Under Pyodide, rendering cost is dominated by Python-to-JS bridge crossings, not by DOM operations. Wybthon never calls DOM APIs directly: the reconciler emits compact ops against integer node ids into a command buffer, and each commit hands the whole buffer to a small JavaScript kernel in a single crossing. A logical update (a `render`, a flush, an event handler) costs one crossing regardless of how many nodes it touches. Event delegation lives in the kernel too, so a click dispatches to Python once, with its payload serialized as one string.

## One flush, three phases

Signal writes are staged. A flush (a microtask, the end of an event handler, or an explicit [`flush`][wybthon.flush]) commits them, runs the render effects (holes and prop bindings), commits the DOM ops across the bridge once, and then runs user effects, which observe the committed DOM. Several writes in one handler therefore produce one flush, one bridge crossing, and one run per affected hole. There is no `batch()` because everything batches.

## Template-based mounting

On top of the command buffer, the reconciler serializes each static host-element skeleton to HTML with its text content hoisted out, registers it with the kernel once, and mounts every occurrence with a single clone op. Structurally identical subtrees (list rows) share one template, so the browser parses the skeleton once and clones it per row, like SolidJS's compiled templates.

You get this for free. Subtrees that can't be expressed as HTML (raw-text elements, adjacent text nodes, and similar) fall back to per-node ops in the same batch with identical behavior. See the [`template`][wybthon.template] API page.

## Authoring tips

### Keep holes small

Embed the accessor (or a lambda that reads it) at the smallest spot in the tree rather than wrapping a large subtree in one expression.

```python
from wybthon import p, span

# One hole around the whole paragraph: the paragraph re-diffs on any change.
p(lambda: f"Hello, {name()}, count={count()}")

# Two text-node holes: each patches exactly one node.
p("Hello, ", span(name), ", count=", span(count))
```

Both are correct; the second does less work per update. The same applies to props: `div(class_=lambda: ...)` re-applies one attribute, while a hole that returns a new `div(...)` re-diffs the element.

### Use keyed `For` for lists

[`For`][wybthon.For] runs its callback once per row and caches the result. On a list change, only added rows map, removed rows dispose, and reorders move existing DOM nodes. Pick the `keyed` mode that matches your data:

- `keyed=True` (default) matches rows by identity (scalars by value). Best for stable objects you mutate through a store.
- `keyed=lambda item: item["id"]` matches by a stable id and updates a row in place when a new object arrives with the same id. Best for data that's replaced wholesale (server responses).
- `keyed=False` matches by position. The DOM never moves; the item accessor of each row updates. Best for fixed-size grids and for scalars where identity is meaningless.

Always pass an accessor for `each`; a plain list renders once and warns in dev mode.

### Use `Repeat` for count-driven UI

When rendering is driven purely by a number (pagination dots, star ratings, skeleton rows), [`Repeat`][wybthon.Repeat] skips list diffing entirely: growing the count mounts new tail slots, shrinking disposes them.

### `peek()` and `untrack` for incidental reads

A read inside a hole, memo, or effect subscribes it. When a value is only needed incidentally, read it with `.peek()` (or wrap several reads in [`untrack`][wybthon.untrack]) so the scope doesn't re-run when it changes. The split form of [`create_effect`][wybthon.create_effect] does this structurally: only the `compute` stage is tracked, and `apply` runs untracked.

```python
from wybthon import create_effect

create_effect(lambda: selected_id(), lambda id: log(id, page_size.peek()))
```

### `equals` to suppress redundant notifications

Signals and memos skip notifying observers when the new value equals the old one (identity fast path, then `==`). For values where `==` is expensive or wrong, pass a custom policy: `equals=lambda a, b: a is b` for identity-only semantics, or `equals=False` to always notify (for example a signal holding a list you mutate in place).

### `create_memo` for shared derivations

A memo computes once per change and serves every reader. Ten holes reading `total()` cost one recomputation, not ten. Memos are lazy, so an unread memo costs nothing.

### `create_selector` for selection state

A naive `lambda: item.id == selected()` in every row re-runs every row when the selection changes. [`create_selector`][wybthon.create_selector] subscribes each key once and notifies only the row that was selected and the one that was deselected, so selecting a row in a 10,000-row table touches two rows.

### `reconcile` for server data

Diffing fresh data into a store with [`reconcile`][wybthon.reconcile] (rather than replacing it) keeps object identities stable and notifies only the leaf signals that changed, so `For` rows for unchanged items keep their DOM.

### Stores over big signals

A signal holding a large dict notifies every reader on any change. A store tracks reads per path: a hole reading `store.user.name` re-runs only when that leaf changes. Use [`deep`][wybthon.deep] when you really want to subscribe to the whole structure (serialization, persistence), and [`snapshot`][wybthon.snapshot] for an untracked plain copy.

### Loading boundaries keep content mounted

[`Loading`][wybthon.Loading] parks its content off-document while pending instead of unmounting it, so async memos created inside keep running, state survives, and revealing the content is a move rather than a mount.

## Runtime considerations

### Garbage collection

The reactive graph holds references from sources to observers and from owners to children, and disposal walks those links. Pyodide's CPython uses reference counting, so most scopes free immediately on unmount. Two habits keep memory flat:

- Dispose what you create outside a component. A memo or effect created at module level under [`create_root`][wybthon.create_root] lives until you call its `dispose`. Prefer creating primitives inside component bodies, where unmount disposes them for you.
- Destroy `pyodide.ffi` proxies you hand to JavaScript (`create_proxy(...).destroy()`) in a cleanup. Wybthon manages the proxies it creates for delegated events and the `popstate` listener.

Wybthon pauses the cyclic collector for the duration of each flush and initial mount and re-enables it afterwards (restoring whatever state it found). A flush allocates in bursts, VNodes, computations, and DOM ops that almost all outlive it, and the collector counts those allocations and would otherwise run several times mid-build, each pass traversing a heap that grows with the app; on a 10,000-row mount that roughly doubled the wall time without freeing anything. Garbage a flush does produce is collected in one pass afterwards. If you profile a hitch in a long-running app that allocates and frees many rows, `gc.freeze()` after startup (to move the framework's long-lived objects out of the collector's view) or a tuned `gc.set_threshold(...)` are the standard CPython levers; measure before applying either.

### Turn off dev mode in production

Dev mode adds the top-level-read check, the write-in-scope check, warning deduplication, and tracebacks in error logs. Call [`set_dev_mode(False)`][wybthon.set_dev_mode] at startup in production builds.

## Micro-benchmarking

Run the included benchmarks against the stubbed DOM:

```bash
python benchmarks/bench_runner.py
```

The app under test is built the idiomatic fine-grained way (mount once, then drive everything through signal writes with `For` and `create_selector`), so the numbers reflect what a well-written Wybthon app pays. The runner measures:

- The standard js-framework-benchmark workloads (create, replace, partial update, select, swap, remove, and clear rows in 1k and 10k row tables); useful as a regression smoke test for the list primitives and the template mount path.
- **`hole update (1k tree)`**: change one signal that drives a single hole inside a 1,000-node tree.
- **`full rerender (1k tree)`**: rebuild the entire tree and let the diffing algorithm reduce the change set to one text node.

Both tree benchmarks update the *same* DOM node; the difference is entirely in *what work the framework does to find the change*. On the stubbed DOM (which makes framework cost more visible than real DOM mutations) the hole update is typically several orders of magnitude faster than the full re-render, which is the whole point of fine-grained reactivity.

Options: `--json` for machine-readable output, `--memory` to include `tracemalloc` measurements, `--bench <substring>` to run a subset, and `--warmup N` and `--iterations N` to override the defaults. `benchmarks/browser_bench.py` runs the real browser app (Pyodide plus headless Chromium) for end-to-end numbers that include the bridge and layout; see `benchmarks/README.md`.

## Next steps

- Read [Mental model](../concepts/mental-model.md) for the underlying ideas.
- Browse [Authoring patterns](authoring-patterns.md) for hole-friendly recipes.
- See [Async and Loading](../concepts/async-loading.md) for code splitting with `lazy`.
