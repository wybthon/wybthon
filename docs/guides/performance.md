# Performance

Wybthon keeps fine-grained dependency tracking and a Virtual DOM that batches native mutations into one bridge crossing per flush. Python execution, serialization, bridge calls, native DOM work, and browser rendering have different costs. Measure the operation you intend to improve.

## Start with startup

Loading and initializing Pyodide takes over a second even with a warm cache, before any Wybthon code runs. For most applications that wait matters more than anything else on this page. [Prerender](../concepts/server-rendering.md) the pages users land on so their content shows immediately, and build with the same Python version as the Pyodide runtime so the archives ship precompiled bytecode (see [Deployment](deployment.md#bytecode)). Production builds also turn dev mode off, so they skip the development checks and warnings.

## What the engine does for you

Rendering cost in Wybthon is mostly Python bookkeeping, not browser DOM work, so the engine's fast paths target the Python side. None of them needs a different component API.

- **Compiled shapes.** The first time an element subtree of a given shape mounts, Wybthon records its static skeleton, its text slots, and where its bindings and dynamic children sit. A repeated shape gets a generated mount function that runs in straight-line code: it checks the instance's structure, allocates node ids, and wires handlers, bindings, and holes by offset. A structural mismatch falls back to the generic path, so correctness never depends on the shape cache.
- **One command per row.** A compiled mount sends one fused `CLONE` command that clones the pre-parsed skeleton, fills its text slots, marks its delegated listeners, and inserts it. Event handlers on template nodes need no per-handler `LISTEN` command. A typical table row costs two kernel commands instead of seven.
- **Native disposal.** Removing a range or a subtree releases every node inside it in the JavaScript kernel, which walks the removed nodes natively. Python finds its own registrations (handlers, reactive bindings, refs) through each shape's binding offsets instead of visiting every node. Clearing a `For` list is one range removal plus disposal of each row's owner.
- **Bulk replacement.** When a keyed list reuses none of its rows, the old rows go in one `DISPOSE_RANGE` command and the new rows mount as one splice, instead of reconciling every unrelated pair.
- **Text placeholders.** A hole whose neighbors aren't text uses a text-node placeholder, so a text result is a plain `nodeValue` write rather than a node replacement.
- **Lighter computations.** Rarely used reactive state (async, transitions, error handlers) lives in a side record allocated on first use, so each render binding allocates and disposes less.

## Use the incremental paths

- Pass a store list directly through a `For` accessor. Local draft edits can use its change records. A list comprehension creates a replacement list that needs generic matching.
- Select rows with a projection. Each row reads its own key, so a selection change notifies only the old and new rows, not every row:

    ```python
    from wybthon import For, component, create_projection, create_signal, li, ul


    @component
    def Rows():
        rows, set_rows = create_signal([{"id": i, "label": f"Row {i}"} for i in range(1000)])
        selected, set_selected = create_signal(None)
        is_selected = create_projection(lambda: {} if selected() is None else {selected(): True})
        return ul(
            For(
                rows,
                lambda row, i: li(
                    row["label"],
                    class_=lambda: "danger" if is_selected.get(row["id"]) else "",
                    on_click=lambda: set_selected(row["id"]),
                ),
            )
        )
    ```

    `is_selected.get(key)` is tracked per key and returns `None` when the key is absent.

- Use `Repeat(count, row)` for integer slots. Growing it mounts only the new slots.
- Keep component setup stable and place dynamic reads in accessors, t-strings, holes, or attribute expressions. Components don't rerun for ordinary state updates.
- Keep row markup consistent. Rows with the same structure share one compiled shape; rows whose structure varies (a conditional element in one branch, for example) mount on the generic path. Put the variation inside a hole instead.
- Use [`VirtualFor`][wybthon.virtual.VirtualFor] for large scrollable collections with fixed row heights. Offscreen rows are disposed, so store durable row state outside the row component.

```python
from wybthon import create_signal, p
from wybthon.virtual import VirtualFor

records, set_records = create_signal([{"name": f"Record {i}"} for i in range(10_000)])

VirtualFor(records, lambda item, index: p(item["name"]), row_height=32, height=400, overscan=4)
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

Profiling is opt-in. Reports include computation runs, rows created, list entries scanned, edit records, commits, DOM commands, serialized bytes, and serialization and kernel time when those operations occur. `template_recipe_hits` counts mounts that reused a compiled shape; `template_shape_walks` counts mounts that had to discover a shape first. A list whose rows mostly walk instead of hitting a recipe has varying structure worth unifying. `inspect_graph(owner)` reports ownership and dependencies without evaluating values.

The repository's `benchmarks/check_work.py` gates command counts in CI: appending 1,000 rows must emit 1,000 row commands, and selection and swap must each emit two. Work counts are deterministic, so they make better regression gates than timings.

## Browser benchmark

```bash
uv sync --locked --group dev
uv run playwright install chromium
uv run python benchmarks/browser_bench.py --mode signal --json
uv run python benchmarks/browser_bench.py --mode store --json
```

The benchmark drives ordinary delegated button events. Each scenario restores its own baseline, warms up, checks that the DOM actually changed, and reports separate synchronous commit and input-to-frame samples. Append starts from 10,000 rows and verifies 11,000 afterward. Selection toggles between distinct rows.

Run comparisons serially on the same browser, runtime, hardware, and cache conditions. Use repeated samples and operation counts; don't turn a single local timing into a universal threshold. CI gates deterministic work contracts and saves browser measurements as artifacts. Production startup is measured separately by the generated loader.

`benchmarks/compare_browser.py --baseline /path/to/baseline` alternates identical operations between isolated checkouts, with five measured samples by default. It measures direct Python operations separately from delegated event dispatch. Use `--mode store` for store comparisons and `--profile` for additional, untimed CPU profiles.

A general store splice can rebuild a persistent sequence. Arbitrary replacement lists still require linear matching. Removing a row shifts following indices. Virtualization is the appropriate tool when mounting the entire collection is the dominant cost.

## Diagnose pending publication

Use `diagnostics.inspect_transitions()` to see which computations and actions hold each dependency group. `diagnostics.inspect_graph(owner)` includes read modes, group IDs, and provisional owners. An ordinary consumer of two pending results joins their groups; a separate `latest()` or `is_pending()` binding can publish during the hold. See [Runtime contracts](../concepts/runtime-contracts.md) for the read and ownership rules.

A transition that remains open retains the values and resources still used by the visible UI. Dispose unused scopes and ensure application actions can finish or be canceled. The native async benchmark reports independent publication at increasing widths; its times exclude browser and network costs.
