# RFC 0005: Engine v5: a lean runtime

- **Status:** Implemented
- **Author:** Owen Carey
- **Created:** 2026-10-22

## Summary

Make Wybthon's per-node cost a fraction of what it is today, without changing how applications are written. Wybthon already matches Solid 2.0's API and mental model, and its update paths are fast; what's slow is creating and disposing nodes, which costs several times what the work itself requires. Engine v5 rebuilds the parts of the runtime every mounted node passes through:

1. **Bindings in one step.** A binding (an attribute, a text slot, a hole, a branch) is created, run, and applied by one straight-line routine, falling back to the general scheduler only while a transition, an action, a server session, or an unpublished preparation is involved.
2. **A smaller computation.** Fields most computations never set move into one extension record, and a computation's links to a single source or a single observer are stored directly instead of in a dictionary.
3. **Text slots without hole nodes.** A child slot whose expression returns text binds straight to its placeholder, and becomes a hole region only if the expression ever returns nodes.
4. **Rows, branches, and components without closures.** `For` mounts and disposes template rows through a direct path; `Show` and `Switch` regions are objects rather than closures over lists; mounting a component calls fewer layers.
5. **A compiler that skips the t-string at run time.** A compiled `html(t"...")` call becomes a call that hands the literal's entry a tuple of values, so no `Template` or `Interpolation` objects are built per instance, and each slot's binder is picked when the module is compiled.
6. **Memory without the cycle collector.** Disposal breaks every reference cycle the engine creates, so removed DOM is freed by reference counting; in the browser, the collection a commit defers runs when the page is idle.
7. **A leaner kernel.** The JavaScript kernel registers only the template nodes Python can address, never deletes properties from DOM nodes, and clears a list that fills its parent by emptying the parent.

The virtual DOM, the batched JavaScript kernel, the reactive semantics, and the public API stay as they are.

## Motivation

### Parity isn't the gap any more

Solid 2.0 still has no stable release: npm's `latest` tag is `solid-js@1.9.17`, and `next` is `2.0.0-rc.17`, the release Wybthon tracks. Comparing RC.17's type declarations and migration guide with Wybthon's API turns up only deliberate differences (lowercase `onclick` in templates, `async def` actions instead of generator actions). There's nothing large left to adopt.

### Creating nodes is slow; updating them isn't

The js-framework-benchmark table, measured on an idle machine with v0.39.0:

| Operation | Browser commit (Chromium, Pyodide 314.0.6) | Native CPU |
| --- | ---: | ---: |
| Create 1,000 rows | 58.7 ms | 22.5 ms |
| Create 10,000 rows | 633.4 ms | 254.1 ms |
| Clear 10,000 rows | 240.2 ms | 63.4 ms |
| Update every tenth of 10,000 | 10.5 ms | 5.0 ms |
| Select a row of 10,000 | 0.5 ms | 0.2 ms |

Updates cost what they should. Creation runs at about 22 µs per row natively and about 59 µs in the browser, where Solid's script time for the same rows is a few microseconds. Mounting a small component (a `Card` with two text bindings, a handler, and a `Show`) costs about 60 µs natively and makes 215 Python calls.

### The work itself is cheap

A deliberately minimal pure-Python prototype that does the same core work per row (one clone command, one tracked attribute computation, a signal bound to a text node, two handlers, and serializing the commands) mounts 1,000 rows in about 4 ms. It skips some real work, such as the projection read and list bookkeeping, but it shows that most of today's 22 ms is framework layering, not Python's speed.

Measuring the pieces a row is made of shows where the layering is:

| Step (native) | Cost |
| --- | ---: |
| Create a reactive attribute binding that reads a signal | 3.65 µs |
| of which: constructing the `Computation` (40 slots) | 0.79 µs |
| Bind a child slot to a signal | 3.86 µs |
| Register a delegated handler | 0.41 µs |
| Build a 4-slot t-string | 0.25 µs |

Creating a binding goes through `_bind_reactive_prop`, `Computation.__init__`, `_add_child`, `_update_if_necessary`, `_update`, `_settle`, `_run_apply`, `_pending_preparation`, the apply function, `_apply_single_prop`, and `_inert`. Nearly every check along the way is for a transition, a preparation, a session, or async work that a fresh binding in an ordinary mount doesn't have. A child slot adds a hole `VNode`, `_mount_hole`'s ten arguments, and a global that routes the first text into the clone command.

### Objects drive the browser's costs

A mounted row keeps 20 objects the cyclic collector tracks: five dictionaries, three functions, three tuples, two computations, two `VNode`s, two handler records, a cell, the row, and a store property. Four of the dictionaries are edge sets holding one entry each, one `VNode` is the text slot's hole, and one tuple is a binding's `(node, name)` pair.

Worse, removed rows are *cyclic garbage*: a row refers to its `VNode` and the `VNode` back to the row, a hole to its binding and back, so nothing a clear removes is freed until the cycle collector finds it. With 10,000 rows mounted after a few clears, the browser app's heap held about 525,000 tracked objects, of which about 300,000 were such garbage, and one full collection took 437 ms. The first collection after a large mount also runs inside the event handler that mounted it: creating 10,000 rows included a 40 to 87 ms collection that freed nothing.

## Design

### 1. Bindings in one step

`_core` gains one constructor for the framework's render bindings:

```python
_bind(fn, apply, data, initial, keep=True, owner=None) -> Computation
```

It builds the computation (assigning its fields directly, without `__init__`), runs `fn` as its observer, and calls `apply(data, value, initial)`, in one function, when the ordinary conditions hold: no observer is running, no transition holds nodes, no action is running, no server or hydration session is active, and the owner isn't inside an unpublished preparation. In that state the general path's checks are all known to pass, so `_bind` skips them. Otherwise it hands the fresh computation to `_update_if_necessary`, exactly as before.

- A result that's awaitable or an async iterator launches as before. A run that created something waiting for publication settles through `_settle`.
- `NotReadyError` keeps the placeholder (`keep`, the default for DOM bindings) or marks the binding pending (`keep=False`, for branch regions); any other exception goes through `_fail`, which routes it to the nearest `Errored` boundary.
- A binding that read nothing and left nothing behind is never attached to its owner. It's applied once and returned marked disposed, with its value in `_value`, so the caller can keep what it rendered.
- When `fn` is a `Signal` (a probe found a signal in a data structure), `_bind` links the two directly instead of calling the signal as a tracked read.
- Probing (an expression the compiler deferred without a call) moves into `_probe_target`, which callers run first: it returns the accessor to bind, or `_STATIC` with the value when the expression reads nothing reactive.

Attribute bindings, text slots, holes, and `Show` and `Switch` regions all create their computations through `_bind`.

### 2. A smaller computation

**The extension record.** Fields that only effects, memos with options, async work, or transitions set (`error_fn`, `lazy`, `unobserved`, `name`, `land_held`, `readiness`, `publication_tx`, `prepared`, `committed`, `apply_cleanup`, `apply_owner`, and `defer`) move into one `_ext` slot holding a `_CompExt` record, created the first time one of them is written. Every hot-path read of one of these fields was a slot read followed by an `is None` test; it's now a read of `_ext` followed by the same test, and several tests collapse into one. A computation drops from 40 slots to 29. This differs from RFC 0003's attempt, which moved fields to class defaults and lost specialization; every field here is still a slot.

**Single links.** A computation's `_sources` and a source's `_observers` hold the lone peer directly while there's exactly one, and become a dictionary when a second arrives. A source read in any mode other than an ordinary tracked read is always stored in a dictionary, so the mode of a single link is always "normal". Three helpers (`_edges`, `_mode`, `_normal_sources`) read either representation outside the hot paths.

**Attribute appliers by name.** Each prop name gets a writer, `writer(node_id, old, new)`, specialized once for that name (the attribute it sets, whether it's a boolean attribute, which DOM property it writes) and cached. An attribute binding's apply stage is a function made once per name from its writer, so the binding's data is its node id alone, with no `(node, name)` tuple.

### 3. Text slots without hole nodes

A template child slot whose value is an accessor or a getter, in a text placeholder, becomes a text binding: a computation whose apply stage writes text into the placeholder, and whose data is the placeholder's id. Its first text fills the clone command's text slot directly. `None` and booleans render as empty text, as in Solid.

If the expression later returns anything else (a node, a list), the binding upgrades in place: it creates the hole region it would have had, takes the hole as its data and `_apply_hole` as its apply stage, and from then on applies through the hole. The region's nodes go in front of the placeholder, and the kernel inserts in front of an anchor into the anchor's live parent, so the binding needs no parent id. A slot's state on a mounted instance is static text, a text binding (possibly upgraded), or a hole; patching and disposing handle all three.

### 4. Rows, branches, and components

- **Rows.** `reconciler._mount_owned` mounts a row (or branch) under its own owner, calling a template row's compiled mount function directly. Callback bodies run through `_run_callback_body(owner, scope, fn, *args)`, with no per-row lambda. `For` keys rows by identity without a call per row for entities.
- **Branches.** `Show`, `Switch`, and `Match` mount as `_BranchRegion` objects, like list regions, instead of closures over one-element lists. A branch with nothing to show (a `Show` without a fallback) mounts no node and allocates no scope. A condition that reads nothing reactive selects its branch once and keeps no computation.
- **Components.** A component's scope is set up without `Owner.__init__`, and the hot mount paths no longer import modules per call.
- **Disposal.** A template instance records which slots hold bindings and regions, and disposes only those. A binding that owns nothing and has no readers disposes in one step.

### 5. The compiler skips the t-string

The compiler already parses each literal and writes its mount functions into the module. It now also replaces the call itself:

```python
html(t'<li class={"on" if active() else ""}>{label}</li>')
# compiles to
__wybthon_t0__.render((lambda: "on" if active() else "", label))
```

- No `Template` or `Interpolation` is built per instance, and `html()` isn't called: the compiler folds a static interpolation's conversion and format spec into an eager `__wybthon__.formatted(value, conversion, spec)` call (which stays reactive for an accessor), as it already folded a dynamic one's into its getter.
- The precompiled entry records which slots always hold a getter the compiler made (`deferred`). The generated mount function binds those slots with `prop_fn` and `child_fn`, which skip classifying the value.
- `html()` keeps compiling templates at run time when it's called with a t-string that wasn't compiled (a REPL, `exec`), with the dev-mode check for those.
- The bytecode cache tag changes to `opt-wyb2`, so modules compiled by v0.39.0 are compiled again.

### 6. Memory without the cycle collector

**Disposal breaks cycles.** Disposing a computation drops its function, apply stage, and data; a disposed row lets go of its `VNode`; a disposed list or branch region and its `VNode` let go of each other; a component's scope no longer refers to its `VNode` at all. Removed rows, components, and holes are freed by reference counting the moment they're removed, and the cycle collector never sees them.

**Readiness only when it matters.** A read of a derived store subscribes to the derivation's readiness only while the derivation is async or has failed. A settled synchronous projection (the selection idiom) costs each reader one field subscription, so a row's selection binding has a single source and the projection no longer collects one readiness observer per row.

**The collector runs when the page is idle.** A flush or mount still pauses the cyclic collector. In the browser, `_gc_resume` no longer re-enables it at the end of the window: a `requestIdleCallback` re-enables it and runs the young collection the window deferred, after the committed DOM has painted. Removing more than 64 rows at once also hands their nodes to that idle callback to free. Outside a browser (CPython, tests, server rendering), the collector is re-enabled at once, as before.

**Freezing was rejected.** `gc.freeze()` after a large mount would keep the collector from ever traversing the mounted objects again, but a reference cycle that application code creates (a nested function that calls itself, an object holding its own bound method) inside a frozen object would never be collected. Deferring the collection to idle time takes it off the interaction path without that risk.

### 7. A leaner kernel

- **Addressed nodes only.** `REGISTER_TPL` gains a seventh field, the template's addressed node offsets: the root, every slot's node and its parent, text slots, and handler nodes. A clone registers only those nodes; the others are never looked up. The benchmark row registers 6 of its 10 nodes.
- **No `delete` on DOM nodes.** Releasing a node used to `delete` its `__wybId` and `__wybL` expandos, which turns the node's wrapper into a slow dictionary-mode object. A released node keeps `__wybId` (lookups already check that the registry maps it back to the node), and `__wybL` is set to `undefined`.
- **Clearing a parent.** When a disposed range is all of its parent's content but at most four nodes (a list's markers and its slot's placeholder), the kernel empties the parent with `textContent = ""` and puts those nodes back, as Solid clears a list.

### What doesn't change

- The public API, the reactive semantics, transitions, async, stores, server rendering, hydration, and the kernel's other commands.
- The VNode tree for `h()` and for templates that expand (server rendering, hydration, SVG).

## Breaking changes

Applications don't change, with one behavior change for derived stores. Internal interfaces do:

| Removed or changed | Replacement |
| --- | --- |
| `html(template, compiled)` (the compiler's second argument) | `html(template)`; a compiled call is `entry.render(values)` |
| `templates.Precompiled(strings, data, factories, probes)` and `load(template)` | `Precompiled(strings, data, factories, probes, deferred)`, with `load()` and `render(values)` |
| Bytecode cache tag `opt-wyb1` | `opt-wyb2` |
| `Computation` fields listed in section 2 | Read through `_ext`; `_name` is a read-only property |
| A computation's `_sources` and a source's `_observers` were always dictionaries | A single peer, or a dictionary; use `_core._edges` and `_core._mode` |
| `_ComponentContext._vnode` | Removed |
| `reconciler._mount_hole`'s template arguments (`end_id`, `ns`, `text`, `clone`, `slot`, `getter`, `probe`) and `reconciler._clone_slot` | `templates` binds child slots itself |
| `_dom_props._apply_binding` | `_dom_props._applier(name)` and `writer(name)` |
| `REGISTER_TPL` had six fields | Seven: the addressed node offsets (registers every node when absent) |
| `Show` with a falsy condition and no fallback mounted an empty text node | It mounts nothing |
| A synchronous derived store that later returns an awaitable reported pending to every reader | Only to readers that read it while it was async; make a loading derivation an `async def` |

## Alternatives considered

**A native reactive core (C or Rust compiled to WebAssembly).** It would make graph bookkeeping several times faster, but the prototype shows that most of the cost is layering that pure Python can drop, and a native core needs a wheel per Pyodide ABI and a pure-Python twin for tests. Worth revisiting after this RFC.

**A separate binding class.** A `RenderBinding` type with its own methods would be smaller still, but every computation that reaches the scheduler would then be one of two types, which RFC 0004 measured costing 8% on the hottest reads. A one-step constructor gets most of the benefit with one type.

**Moving fields to class defaults.** RFC 0003 tried it: reads of class defaults on instances with a `__dict__` aren't specialized and were 3.5 times slower. The extension record keeps every read a slot read.

**Freezing the heap after large mounts.** See section 6.

**Unlisted template bindings and intrusive child lists.** Not registering a template's bindings with their owner, or linking an owner's children through the children themselves, would each remove the dictionary a row keeps for its two bindings. The first hides bindings from `inspect_graph` and the second adds three slots to every owner; neither is worth one object per row.

**Do nothing.** Mounting stays about twice as slow as it needs to be, and every clear leaves its rows for the cycle collector.

## Drawbacks and risks

- **Two paths for a binding's first run.** The fast path must agree with the general one. Its conditions are checked once per binding, and the test suite exercises both: the general path runs whenever a transition, an action, a session, or a preparation is active.
- **Single links add a branch** to every edge operation. The branch is a type test on an object the code already holds.
- **Upgradable text bindings** make a child slot's state one of three kinds instead of two.
- **Idle-time collection** delays collecting cyclic garbage that application code creates until the page is idle (at most a second, `requestIdleCallback`'s timeout).
- **Every compiled module recompiles**, once, because of the new cache tag.

## Testing

- The unit suite (now 933 tests) and the browser suite on Pyodide (84 tests), with tests of removed internals adapted.
- `tests/test_engine_v5.py` covers: `_bind`'s fast path and its general path in an action; inert bindings; errors routed to boundaries; async placeholders; the extension record; single links growing into dictionaries and both sides released on disposal; text bindings upgrading to holes, rendering `None`, and being disposed and patched; `Show` without a fallback; the compiler's `render` calls, folded format specs, and binder choice; the cache tag; addressed template nodes; that clearing rows and components leaves no framework objects for the cycle collector; the collector's pause and release; and single-field subscriptions to a settled projection.
- Work gates in `benchmarks/check_work.py` unchanged.
- Benchmarks, native and browser, against v0.39.0. Targets:
  - creating rows at least 2 times faster natively, and at least 1.8 times faster in the browser;
  - clearing rows at least 1.8 times faster natively;
  - at most 12 tracked objects per row;
  - mounting the `Card` component at least 2 times faster natively;
  - updates no slower.

### Results

The [engine v5 evaluation](https://github.com/wybthon/wybthon/blob/main/benchmarks/results/engine-v5.md) measured the implementation against v0.39.0 (`7597147`) on an idle machine.

- **Native CPU time, by the median of per-round ratios:** creating 1,000 rows 2.19 times faster and 10,000 rows 2.06 times; replacing 2.01 times; appending 2.02 times; updating every tenth row 1.36 times; swapping 1.30 times; clearing 1.51 to 1.71 times. Without the selection binding, creating 1,000 rows is 2.66 times faster.
- **Components:** mounting 1,000 `Card` components 1.97 times faster, and clearing them 1.81 times.
- **Work:** creating 1,000 rows makes 61,103 function calls instead of 101,100. A row keeps 15 tracked objects instead of 20 (10 instead of 13 without selection) and 2,464 bytes instead of 3,856.
- **Memory:** clearing rows or components leaves no cyclic garbage, where v0.39.0 left 9 objects per row and 16 per `Card` row. With 10,000 rows mounted after earlier clears, the browser app's collector tracks 264,738 objects instead of 894,609, and a full collection takes 88 ms instead of 1,375 ms.
- **Browser, signal mode:** creating 1,000 rows 1.75 times faster (58.7 ms to 33.6 ms) and 10,000 rows 2.03 times (536.6 ms to 263.9 ms); clearing 10,000 rows 2.00 times, with the kernel's share halved (129.7 ms to 64.2 ms); appending 1.69 times; updates 1.00 to 1.37 times. Time to the next frame after creating 10,000 rows fell from 691 ms to 265 ms, because the collection the mount owes now runs when the page is idle.
- **Browser, store mode:** creating rows 1.46 to 1.65 times faster, clearing 1.58 times, updating every tenth row 1.09 times.
- **Startup:** unchanged (1,535 ms to 1,525 ms to ready).

| Target | Result |
| --- | --- |
| Creating rows at least 2 times faster natively | Met: 2.19x for 1,000 rows and 2.06x for 10,000 |
| Creating rows at least 1.8 times faster in the browser | Partly met: 2.03x for 10,000 rows and 1.75x for 1,000 in signal mode; 1.46x to 1.65x in store mode |
| Clearing rows at least 1.8 times faster natively | Missed natively (1.51x to 1.71x), where a clear now also frees its rows; met in the browser in signal mode (2.00x) |
| At most 12 tracked objects per row | Missed: 15 with the selection binding, 10 without |
| Mounting the `Card` component at least 2 times faster natively | Nearly met: 1.97x |
| Updates no slower | Met |

The largest remaining costs per row are the projection's field subscription and the binding that reads it, the two handler records, and the dictionary of a row's children; the next step for the object count is an intrusive child list on `Owner`.

## Unresolved questions

- Whether `Owner` should link its children intrusively, which would remove the last dictionary a row keeps.
- Whether the compiler should emit binders for static `h()` trees too.

## Decision

Accepted on 2026-10-22. Wybthon is pre-1.0 and has no production users yet, so the internal changes ship without a compatibility layer.
