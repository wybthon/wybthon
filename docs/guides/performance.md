# Performance

Wybthon keeps fine-grained dependency tracking and a Virtual DOM that batches native mutations into one bridge crossing per flush. Python execution, serialization, bridge calls, native DOM work, and browser rendering have different costs. Measure the operation you intend to improve.

## Start with startup

Loading and initializing Pyodide takes over a second even with a warm cache, before any Wybthon code runs. For most applications that wait matters more than anything else on this page.

- **Prerender the pages users land on.** [Server rendering](../concepts/server-rendering.md) puts their content on screen at first paint, and the page hydrates once Python is ready.
- **Ship bytecode.** Build with the same Python version as the Pyodide runtime so the archives include precompiled bytecode and the browser doesn't compile Wybthon or your application at startup (see [Deployment](deployment.md#bytecode)).
- **Let the build start downloads early.** `wyb build` inlines the manifest into the page and emits preload hints for Pyodide's module and both archives, so the browser starts fetching them while the page parses instead of after the bootstrap runs.
- **Keep the first import small.** Load routes and heavy components with [`lazy`][wybthon.lazy], and move rarely used code into [explicit chunks](deployment.md#explicit-lazy-chunks).

Production builds also turn dev mode off, so they skip the development checks and warnings.

## What the engine does for you

Rendering cost in Wybthon is mostly Python bookkeeping, not browser DOM work, so the engine's fast paths target the Python side.

- **Templates compile once per literal.** A t-string literal hands [`html`][wybthon.html] the same static strings on every call, so Wybthon parses and compiles each literal once. The static markup becomes a native `<template>`, and each instance mounts with one fused `CLONE` command that clones it, fills its text slots, marks its delegated listeners, and inserts it. No VNode tree is built for static parts, and nothing is checked node by node: the literal guarantees its own structure. See [Templates](../concepts/templates.md#why-templates).
- **Components cost what their markup costs.** A component can only receive new props when a reactive hole re-renders a tree that contains it (or `render` runs again into the same container). Everywhere else (another component's output, a list row, a `Show` branch, a template slot), a prop passed as a constant subscribes to nothing; a prop passed as an accessor subscribes the reader directly.
- **Inert bindings are dropped.** A hole or attribute binding that finishes its first run without reading anything reactive (and without creating children, cleanups, or async work) can never run again, so Wybthon disposes it immediately and keeps only the DOM it produced.
- **Native control flow.** `Show`, `For`, `Repeat`, and `Switch` mount as regions the reconciler manages directly, with no component, props object, or wrapper memo. When a hole re-renders one of them, the new condition or source is pushed into the mounted region instead of remounting it.
- **Native disposal.** Removing a range or a subtree releases every node inside it in the JavaScript kernel, which walks the removed nodes natively. Python releases its own registrations (handlers, reactive bindings, refs) without visiting every node. Clearing a `For` list is one range removal plus disposal of each row's owner.
- **Bulk replacement.** When a keyed list reuses none of its rows, the old rows go in one `DISPOSE_RANGE` command and the new rows mount as one splice, instead of reconciling every unrelated pair.
- **Text placeholders.** A hole whose neighbors aren't text uses a text-node placeholder, so a text result is a plain `nodeValue` write rather than a node replacement.
- **Lighter computations.** Async state lives outside each computation until a computation actually runs async work, so an ordinary render binding doesn't allocate it.

## Templates and element helpers

Both styles share one set of prop appliers, so they behave the same; they differ in what happens before mounting.

- A **template** costs one cached lookup per call, then one clone. Its structure is fixed by the literal.
- An **element helper** tree is built as VNodes on every call. Wybthon compiles each repeated helper shape at run time, so a repeated row still mounts with one clone command, but every instance pays for building its VNodes and for matching them against the compiled shape. A helper subtree whose structure varies (a conditional element in one branch, for example) mounts on the generic path.

Use templates for markup you write by hand, and especially for list rows. Use the helpers where markup is built by code. In a helper tree, keep row structure consistent and put any variation inside a hole.

## Use the incremental paths

- **Pass accessors instead of re-rendering holes.** Put a signal straight into the markup (`<b title={role}>{name}</b>`) and only that attribute or text node updates. A hole that returns a subtree re-runs as a whole: a template from the same literal is patched slot by slot, but anything else is rebuilt. Pass accessors to components too: a hole that rebuilds `Card(title=title())` patches the component on every change, while `Card(title=title)` placed once never re-runs.
- **Keep holes small.** A function hole around a single text node patches one node.
- **Pass a store list directly through a `For` accessor.** Local draft edits can use its change records. A list comprehension creates a replacement list that needs generic matching.
- **Select rows with a projection.** Each row reads its own key, so a selection change notifies only the old and new rows, not every row:

    ```python
    from wybthon import For, component, create_projection, create_signal, html


    @component
    def Rows():
        rows, set_rows = create_signal([{"id": i, "label": f"Row {i}"} for i in range(1000)])
        selected, set_selected = create_signal(None)
        is_selected = create_projection(lambda: {} if selected() is None else {selected(): True})

        def row(item, index):
            def row_class():
                return "danger" if is_selected.get(item["id"]) else ""

            def select():
                set_selected(item["id"])

            return html(t"<li class={row_class} onclick={select}>{item['label']}</li>")

        return html(t"<ul>{For(rows, row)}</ul>")
    ```

    `is_selected.get(key)` is tracked per key and returns `None` when the key is absent. Each row mounts with one clone command, and a selection change sends one command per affected row.

- **Use `Repeat(count, row)` for integer slots.** Growing it mounts only the new slots.
- **Keep component setup stable.** Place dynamic reads in accessors, holes, or attribute expressions. Components don't rerun for ordinary state updates.
- **Virtualize large collections.** Use [`VirtualFor`][wybthon.virtual.VirtualFor] for large scrollable collections with fixed row heights. Offscreen rows are disposed, so store durable row state outside the row component.

```python
from wybthon import create_signal, html
from wybthon.virtual import VirtualFor

records, set_records = create_signal([{"name": f"Record {i}"} for i in range(10_000)])


def record(item, index):
    return html(t"<p>{item['name']}</p>")


VirtualFor(records, record, row_height=32, height=400, overscan=4)
```

`map_cooperative(items, fn, budget_ms=8)` from `wybthon.scheduling` yields between chunks of expensive Python work, and `yield_to_browser()` provides an explicit cooperative yield. A single expensive callback still blocks until it returns; these helpers don't preempt Python or replace a worker.

## Measure work as well as time

```python
from wybthon import create_root, create_store, flush
from wybthon.diagnostics import profile, runtime_stats

store, edit = create_root(lambda dispose: create_store({"rows": []}))

with profile() as measured:
    edit(lambda draft: draft["rows"].append({"id": 1}))
    flush()
print(measured.as_dict())
print(runtime_stats())
```

Profiling is opt-in. Reports include computation runs, rows created, list entries scanned, edit records, commits, DOM commands, serialized bytes, and serialization and kernel time when those operations occur. `template_clones` counts template instances mounted by cloning. For element helpers, `template_recipe_hits` counts mounts that reused a compiled shape, and `template_shape_walks` counts mounts that had to discover a shape first; a helper list whose rows mostly walk instead of hitting a recipe has varying structure worth unifying. `inspect_graph(owner)` reports ownership and dependencies without evaluating values.

The repository's `benchmarks/check_work.py` gates command counts in CI: appending 1,000 rows must create 1,000 rows with one clone command each (counting both template clones and compiled helper shapes), and selection and swap must each emit at most two commands. Work counts are deterministic, so they make better regression gates than timings.

## Benchmarks

```bash
uv sync --locked --group dev
uv run playwright install chromium
uv run python benchmarks/browser_bench.py --mode signal --json
uv run python benchmarks/browser_bench.py --mode store --json
```

The browser benchmark builds the benchmark app (an ordinary project in `benchmarks/app`) with `wyb build`, serves it, and drives ordinary delegated button events. Each scenario restores its own baseline, warms up, checks that the DOM actually changed, and reports separate synchronous commit and input-to-frame samples. Append starts from 10,000 rows and verifies 11,000 afterward. Selection toggles between distinct rows.

Run comparisons serially on the same browser, runtime, hardware, and cache conditions. Use repeated samples and operation counts; don't turn a single local timing into a universal threshold. CI gates deterministic work contracts and saves browser measurements as artifacts. Production startup is measured separately by the generated loader.

`benchmarks/compare_browser.py --baseline /path/to/baseline` alternates identical operations between isolated checkouts, building each one, with five measured samples by default. It measures direct Python operations separately from delegated event dispatch. Use `--mode store` for store comparisons and `--profile` for additional, untimed CPU profiles.

`benchmarks/row_bench.py` times the same table operations in plain CPython against any checkout's sources, reporting Python's share of the work and the commands each operation sends. Pass `--template` to write the rows as `html` templates instead of element helpers.

Recorded measurements, with the hardware and versions they were taken on, live in [`benchmarks/results/`](https://github.com/wybthon/wybthon/tree/main/benchmarks/results); [`engine-v3.md`](https://github.com/wybthon/wybthon/blob/main/benchmarks/results/engine-v3.md) compares this engine with the previous release.

A general store splice can rebuild a persistent sequence. Arbitrary replacement lists still require linear matching. Removing a row shifts following indices. Virtualization is the appropriate tool when mounting the entire collection is the dominant cost.

## Diagnose pending publication

Use `diagnostics.inspect_transitions()` to see which computations and actions hold each dependency group. `diagnostics.inspect_graph(owner)` includes read modes, group IDs, and provisional owners. An ordinary consumer of two pending results joins their groups; a separate `latest()` or `is_pending()` binding can publish during the hold. See [Runtime contracts](../concepts/runtime-contracts.md) for the read and ownership rules.

A transition that remains open retains the values and resources still used by the visible UI. Dispose unused scopes and ensure application actions can finish or be canceled. The native async benchmark reports independent publication at increasing widths; its times exclude browser and network costs.
