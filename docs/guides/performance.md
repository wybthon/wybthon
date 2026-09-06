# Performance

Wybthon keeps fine-grained dependency tracking and a Virtual DOM that batches native mutations. Python execution, serialization, bridge calls, native DOM work, and browser rendering have different costs. Measure the operation you intend to improve.

## Use the incremental paths

- Pass a store list directly through a `For` accessor. Local draft edits can use its change records. A list comprehension creates a replacement list that needs generic matching.
- Use `create_selector(selected)` for selected-row flags. With ordinary equality, only the old and new keys are notified. A custom comparator may need to visit all subscribed keys.
- Use `Repeat(count, row)` for integer slots. Growing it mounts only the new slots.
- Keep component setup stable and place dynamic reads in accessors, holes, or prop expressions. Components don't rerun for ordinary state updates.
- Use `VirtualFor` for large scrollable collections with fixed row heights. Offscreen rows are disposed, so store durable row state outside the row component.

```python
from wybthon import VirtualFor, p

VirtualFor(lambda: records, lambda item, index: p(lambda: item.name),
           row_height=32, height=400, overscan=4)
```

`map_cooperative(items, fn, budget_ms=8)` yields between chunks of expensive Python work. `yield_to_browser()` provides an explicit cooperative yield. A single expensive callback still blocks until it returns; these helpers don't preempt Python or replace a worker.

## Measure work as well as time

```python
from wybthon import flush
from wybthon.diagnostics import profile, runtime_stats

with profile() as measured:
    edit(lambda draft: draft.append(new_row))
    flush()
print(measured.as_dict())
print(runtime_stats())
```

Profiling is opt-in. Reports include computation runs, rows created, list entries scanned, edit records, commits, DOM commands, serialized bytes, and serialization/kernel time when those operations occur. `template_recipe_hits` counts mounts that reuse a prepared extraction routine; `template_shape_walks` counts mounts that need generic template discovery. `inspect_graph(owner)` reports ownership and dependencies without evaluating values.

Template prototypes are bounded and reused across varying instance attributes. Text-only holes reuse their anchor handle as the text node. Range operations move or remove fragment rows in one command. Keep the JSON command transport unless profiling demonstrates a better tradeoff.

Repeated VDOM shapes also reuse bounded Python extraction routines. Each mount checks the tree's structure, static attributes, and binding kinds before reusing a routine. Changed shapes fall back to ordinary template discovery. Handlers, refs, and reactive expressions come from the current VNode instance. This happens at runtime and doesn't require a compiler or a different component API.

Direct signal bindings retain their dependency instead of rebuilding it on each update. Stores allocate length, key, and subtree subscriptions when they're first observed. These optimizations preserve staged writes, transition visibility, cleanup, and dynamic dependency tracking.

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
