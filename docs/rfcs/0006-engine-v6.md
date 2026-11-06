# RFC 0006: Engine v6: fast pages

- **Status:** Implemented
- **Author:** Owen Carey
- **Created:** 2026-11-05

## Summary

Make a Wybthon page fast to show and fast to start, and make editing one fast to see. Five engine releases have brought updating and mounting DOM close to what Python can do. What's slow now is everything around it: starting Pyodide, rendering on the server, and the development loop. Engine v6 changes four things:

1. **Boot snapshots.** After a page's first boot, the bootstrap builds a memory snapshot of a Pyodide runtime with Wybthon imported, in a worker, and stores it. Later visits, and every `wyb dev` reload, restore it instead of starting Python.
2. **A string renderer for the server.** Server rendering writes HTML directly instead of mounting the tree into an in-memory DOM and serializing it. The output is byte for byte what it was, so hydration doesn't change.
3. **Hot module replacement in `wyb dev`.** An edited module is replaced in place in the open page, and the components it defines are remounted, instead of the page reloading.
4. **Solid 2.0 RC.21.** `on_flush` and `from_source` are added, and `create_owner` is removed, as in Solid.

The virtual DOM, the batched JavaScript kernel, the client renderer, hydration, and the reactive semantics stay as they are.

## Motivation

### Startup is most of what users wait for

Solid 2.0 still has no stable release: npm's `latest` is `solid-js@1.9.18`, and `next` is `2.0.0-rc.21` (November 4). Every change from RC.17 to RC.21 is a patch-level fix or a small addition, so API parity isn't the gap.

Measured on an Apple M-series laptop with Chromium 151 and Pyodide 314.0.6, the starter app is ready about 800 ms after navigation with a warm HTTP cache, and about 750 ms of that is Pyodide loading and initializing, before any Wybthon code runs. By comparison, the [engine v5 evaluation](0005-engine-v5.md#results) measured creating 1,000 table rows at about 34 ms in the browser. Every user pays the startup on every page load; few pages create thousands of rows.

A spike showed that a memory snapshot changes this. Booting Pyodide normally took about 890 ms in headless Chromium; restoring a snapshot that had already imported the standard library took about 108 ms. A snapshot made in Node restored and ran in Chromium, including access to `js`, and Pyodide 314.0.6 ships the hooks it needs (`_makeSnapshot`, `makeMemorySnapshot`, and `_loadSnapshot`).

### Server rendering costs a hundred times what it should

Server rendering is what keeps a Wybthon page usable while Pyodide starts, and it's the part of Wybthon that runs per request. It ran the full client renderer against a small in-memory DOM: templates were expanded into VNode trees, every node became a kernel command, the commands built a DOM, the DOM was serialized, and the tree was disposed. A simple 1,000-row table took 24 ms in CPython, where writing the same HTML with f-strings takes 0.23 ms. Solid compiles a separate server renderer for the same reason.

### Every edit cost a full boot

`wyb dev` rebuilt on change and reloaded the page, so every saved file paid Pyodide's whole startup again and lost the page's state.

## Design

### 1. Boot snapshots

**Building.** When a boot didn't restore a snapshot and the build has a snapshot key, the bootstrap waits for the page to be idle (`requestIdleCallback`, with a five-second timeout) and starts a module worker from an inline script. The worker loads Pyodide with `_makeSnapshot: true`, fetches and unpacks the runtime archive, imports `wybthon._snapshot` and calls its `preload()`, takes `makeMemorySnapshot()`, and stores the bytes in Cache Storage under a URL derived from the key, deleting older entries. The page records the outcome in `window.__WYB.snapshot` and dispatches `wybthon:snapshot`.

`preload()` imports the framework's browser modules (including the ones `import wybthon` loads on first use, such as `wybthon.store`) and a dozen standard library modules applications commonly import. It doesn't import the application: a module that reads `window` at import time would fail in a worker, and a snapshot can't hold references to JavaScript objects.

**Restoring.** The bootstrap reads the cached snapshot while `pyodide.mjs` loads, and passes it to `loadPyodide` as `_loadSnapshot`. A snapshot that fails to restore is deleted and that boot starts Python normally. Pyodide still mounts its standard library archive, and the file system isn't part of a memory snapshot, so the bootstrap unpacks the runtime and application archives as before; lazy chunks and later imports read them from there. `window.__WYB.timings.snapshot` records whether a boot restored one.

**Keys.** `wyb build` writes a `snapshot` key into the manifest: a hash of the Wybthon version, the Pyodide URL, and the runtime archive's content-hashed name. The application isn't part of it, so a snapshot stays valid across application changes, and every `wyb dev` rebuild restores the snapshot the first load built. The key is `null`, and the page boots normally, when `snapshot = false` is set in `wybthon.toml` or the build loads Pyodide `packages` or `wheels`, which live in the virtual file system rather than in memory.

**Why not ship the snapshot.** The snapshot is 31 MB, 4.1 MB with Brotli. A spike found that a restored runtime still fetches the 2.5 MB standard library archive, so shipping a snapshot from `wyb build` would add 4.1 MB to every first visit to save its startup. Building one in the browser after the first visit costs no download at all. A build-time snapshot remains possible (`wyb build` could make one with Node), and could become an option for deployments where first visits matter most.

### 2. A string renderer for the server

`wybthon._ssr` walks the tree the reconciler mounts and appends HTML to a list of strings. It mirrors each of the reconciler's mount paths:

- **Elements and templates.** An element's props become attributes exactly as the prop writers would set them on a fresh node and the old serializer would write them: classes and styles normalized, boolean attributes, `value` and `checked` as properties, `dataset`, `inner_html`, textarea content, controlled `<select>` options, raw text in `<script>` and `<style>`, void elements, SVG namespaces. A template instance renders from its parsed element and its values, with no VNode tree. Each parsed element gets a plan the first time it renders: a subtree with no interpolations is serialized once and reused, and an element whose attributes are static writes cached tags around its children.
- **Holes, lists, branches, and fragments.** The same comment markers the browser's DOM would contain. A hole's text replaces its anchor; any other result is followed by it. `For` and `Repeat` rows, `Show` and `Switch` branches, and list fallbacks render under owners created as the regions create them.
- **Components.** A component runs once under a component context added to the current owner, with the same position key, so context lookups, `Errored` handlers, and `Loading` registration work exactly as in the browser, and every memo, boundary, and unique id gets the hydration key the browser will ask for.
- **Evaluation.** Each expression is evaluated once, with no observer. Nothing subscribes, so a server render allocates no computations for its bindings. An expression that isn't ready leaves its placeholder; one that raises is routed to the nearest `Errored` boundary. Event handlers and refs aren't attached.
- **`Loading`.** A server version of the boundary registers exactly as the browser's does (hydration key, collector, `Reveal` slot, `on` inputs) and renders its content immediately, so async reads under it register. Whether the output keeps the content or shows the fallback is decided once the whole tree has rendered and the render's flush has run, when every boundary under a `Reveal` has registered: a boundary is a deferred part of the output, resolved in creation order.
- **`Errored`.** The boundary's body is unchanged. When its content raised during the render, its staged error is committed and the boundary's expression is evaluated again, rendering the fallback in place of the discarded content, as the browser's boundary would re-render.

`wybthon.server` keeps its API, its multi-pass resolution of async data, its serialized state, and out-of-order streaming. A pass is now a string render under a session; streaming reads each boundary's resolved content from its part of the output instead of from a DOM. Any kernel command a component emits during a server render is dropped.

**Verification.** During development, the previous server renderer was kept as an oracle. Every server render in the unit suite, all 46 renders of the browser fixture app's routes (each route rendered and awaited), and a corpus of 28 renders covering markup with serialization rules of its own produced byte-identical output. The corpus is now `tests/test_ssr_output.py`, with the oracle's output as its expected HTML.

### 3. Hot module replacement in `wyb dev`

**The server.** The watcher compares modification times before and after each rebuild. When every changed file is an existing Python module in the application directory, it sends an `hmr` event with each file's path and new source and the dotted module names; anything else (a new or deleted file, markup, assets, configuration) sends `reload`.

**The page.** The script `wyb dev` injects sets `globalThis.__wybHot`, which makes the bootstrap call `wybthon._hmr.enable()` before the application imports: from then on the reconciler records every mounted component with its parent node id. On `hmr`, the script writes the sources into the runtime's file system and calls `wybthon._hmr.apply(modules)`. When it returns False, the page reloads.

**Applying.** For each changed module that's been imported, `apply` deletes the module's cached bytecode, compiles the new source with the compiler, and runs it in the module's existing namespace. Then:

- A `Component` that existed before keeps its identity: the old object takes the new function and re-resolves its props class, and the namespace's name is pointed back at it, so modules that imported it render the new code.
- A plain function defined in the module keeps its identity when the new code has the same free variables: its code object, defaults, and annotations are swapped in place.
- Every live instance of a component from a changed module, or from a module of the same package that holds something from one, is a target. The outermost targets (decided before any remount, since remounting a parent detaches its children) run their bodies again in place: the reconciler's `_hot_remount` inserts a marker before the instance's first node, unmounts its old subtree, disposes its context, mounts the component again into the same VNode with the same props under the same parent owner, and removes the marker. Whatever holds the VNode (a parent's subtree, a list row, a hole) keeps working.

`apply` returns False, and the page reloads, when the new code fails to compile or raises, when a module calls `render` or `hydrate` while it runs (the reconciler checks), or when a target rendered nothing it could be located by. State outside the remounted components is kept; their own local state starts over, as with Solid's hot reloading.

Tracking costs one global read per component mount when it's off, and a cleanup per component in `wyb dev` pages.

### 4. Solid 2.0 RC.21

- **`on_flush(fn)`** (Solid's `onFlush`, RC.19) runs `fn` once after the pending flush has committed, outside it, untracked and unowned, so a write it makes schedules an update of its own. Dev mode warns when it's called in a component body or computation. It doesn't run on the server.
- **`from_source(source)`** (Solid's `from`, RC.18; `from` is a Python keyword) adapts a subscribe function `(next, error, complete) -> unsubscribe`, an observable with a `subscribe` method (whose result may have `unsubscribe()` or `dispose()`), or an async iterable into an async generator. Returned from a memo's body, the memo holds the latest value; values pushed faster than it reads them are dropped. The source is closed when the memo re-runs or is disposed, since the memo closes the generator.
- **`create_owner`** is removed, as RC.21 removed `createOwner` from Solid's public types. `create_root` with `get_owner` and `run_with_owner` replaces it.
- Behavior RC.19 to RC.21 fixed that Wybthon already had: each replayed pre-hydration event flushes on its own, `For` doesn't rewrite a retained row whose item didn't change, and a write that nets back to the committed value in the same tick doesn't make anything pending. `use_context` with no owner already returns the context's default.

## Breaking changes

| Removed or changed | Replacement |
| --- | --- |
| `create_owner()` | `create_root(lambda dispose: get_owner())`, or `create_root` with `run_with_owner` |
| `wybthon._server_dom` (`ServerBackend`, `ServerDocument`, `serialize_node`, `inner_html`, `html_between`) | `wybthon._ssr` renders the server's HTML directly |
| `reconciler._server_render` | `_ssr.render` inside a session (see `server._Pass`) |
| `session.boundaries` held `(key, fragment, shown signal)` | `(key, _ssr.Boundary)`; a boundary's `mode` and `inner_html()` |
| The browser `Loading` body registered server boundaries | `loading._server_loading` is the server body |
| A server render called refs with a server element | Refs aren't called on the server; the browser calls them while hydrating |
| A write made while a server render ran re-rendered the holes that read it | Each expression is evaluated once; nothing subscribes on the server |
| `wyb dev` reloaded on every change | An edited application module is replaced in place; other changes reload |
| The manifest had no `snapshot` field | `snapshot`: the boot snapshot key, or `null` |

## Alternatives considered

**Shipping a build-time snapshot.** See section 1: it would add 4.1 MB to every first visit, and it needs Node at build time.

**A cheaper in-memory DOM for the server.** Keeping the mount path but replacing the server backend and serializer would have removed perhaps half the cost; expanding templates, emitting commands, and disposing the tree would remain.

**Generating server render functions in the compiler.** Emitting a string renderer per literal, as Solid's compiler does, would remove the plan lookup and the walk over the parsed tree. The plans get most of the benefit without a second code generator or a new bytecode cache tag, and the walk is shared with templates compiled at run time.

**Owner-based hydration keys.** Solid 2.0 keys hydration by owner (`getNextChildId`). Wybthon keys by position in the tree, which the string renderer reproduces; changing the scheme would have changed hydration too.

**Faster store writes.** A draft edit of a store field costs about three times a signal write. The draft and journal machinery was optimized in v0.33, and what remains needs a redesign of its own; it isn't part of this RFC.

## Drawbacks and risks

- **The snapshot hooks are private.** `_makeSnapshot` and `_loadSnapshot` are underscored Pyodide options. The Pyodide release is pinned per build, the key includes it, and a failed restore falls back to a normal boot.
- **The first visit builds a snapshot in the background:** about a second of a worker thread and 31 MB of Cache Storage.
- **Two renderers must agree.** The browser renderer and the string renderer now implement the same markup separately. `tests/test_ssr_output.py` pins the server's output for the cases with their own serialization rules, and the hydration tests claim server output in both the stub DOM and Chromium.
- **Hot updates re-run module code.** A module with side effects at import time runs them again; one that renders is detected and reloads.

## Testing

- The unit suite (1,002 tests), including `tests/test_ssr_output.py`, `tests/test_rc21.py`, `tests/test_hmr.py`, and `tests/test_boot_snapshot.py`.
- The browser suite on Pyodide 314.0.6 (91 tests), including a snapshot built and restored under `wyb preview` and `wyb dev` (the restored runtime runs the app and loads a lazy chunk), and a hot update under `wyb dev` that keeps state and handlers, followed by a markup change that reloads.
- `benchmarks/ssr_bench.py`, which checks that each page's output matches the baseline checkout's.

### Results

The [engine v6 evaluation](https://github.com/wybthon/wybthon/blob/main/benchmarks/results/engine-v6.md) measured the implementation against v0.40.0.

- **Startup:** a repeat visit to the starter app is ready in 95 ms instead of 799 ms (8.4 times faster), by the median of six alternating boots. Pyodide's share falls from 744 ms to 71 ms. A first visit does the same work as before, plus one Cache Storage lookup.
- **Server rendering:** a 1,000-row table renders 7.1 times faster (41 ms to 5.8 ms), 10,000 rows 7.8 times, 1,000 components 4.0 times, and a page of 50 boundaries 3.2 times, with identical output.
- **Client rendering:** unchanged.

## Unresolved questions

- Whether `wyb build` should offer a shipped snapshot for deployments where first visits dominate.
- Whether hot updates should preserve the local signals of remounted components, as React Fast Refresh preserves hook state.

## Decision

Accepted on 2026-11-05. Wybthon is pre-1.0 and has no production users yet, so the changes ship without a compatibility layer.
