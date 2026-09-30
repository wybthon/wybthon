# RFC 0001: Server rendering, hydration, and the boot pipeline

- **Status:** Implemented
- **Author:** Owen Carey
- **Created:** 2026-09-29
- **Tracking:** [#38](https://github.com/wybthon/wybthon/pull/38)

## Summary

Add server rendering to Wybthon: render a component tree to HTML in CPython, either at request time or at build time, and let the browser *hydrate* that HTML (adopt the existing DOM nodes and attach reactivity to them) instead of building the page from scratch. Resolved async data travels with the HTML so the client neither refetches it nor flashes a loading state. The production build prerenders routes, ships precompiled bytecode, and replays input that arrives before Python is ready. A small sweep aligns the remaining API with the SolidJS 2.0 release candidate.

## Motivation

Wybthon's interactive performance is already good. The browser benchmarks show about 0.4 ms to select a row, about 10 ms to update every tenth row of 10,000, and about 20 ms to swap rows. Mounting is slower (roughly 90 ms for 1,000 rows), but it's in the same order of magnitude as other frameworks once you account for Python running on WebAssembly.

Startup is the real problem. With a warm HTTP cache, loading and initializing Pyodide takes about 1.5 s, importing and starting the application takes about 270 ms more, and the page shows nothing but "Loading..." for roughly 1.8 s. A cold visit also downloads several megabytes of runtime first. No renderer optimization can close that gap, because the time is spent before the renderer runs.

Server rendering can. The page's HTML arrives with the first response, so users see content immediately and search engines index it; Python boots in the background and takes over the existing DOM.

Server rendering is also the largest missing piece of SolidJS parity. Solid ships `renderToString`, `renderToStream`, `hydrate`, `isServer`, per-computation control over where async data resolves (`ssrSource`), and `clientOnly`. Wybthon had none of these.

Wybthon is well placed to add them. Everything already imports and runs in CPython, so the same components can render on a Python server. The renderer already speaks a narrow wire protocol to a pluggable backend, so a server backend is a new implementation of an existing interface rather than a second renderer.

## Design

### Public API

New in `wybthon` (and `wybthon.server` for the server entry points):

```python
from wybthon import hydrate, is_server, client_only
from wybthon.server import render_to_string, render_to_string_async, render_to_stream

html = render_to_string(App(), url="/users/7")              # synchronous; async data renders fallbacks
html = await render_to_string_async(App(), url="/users/7")  # waits for async data and serializes it
async for chunk in render_to_stream(App(), url="/users/7"): # shell first, then each Loading boundary
    await send(chunk)

hydrate(App(), "#app")   # in the browser, instead of render(App(), "#app")
```

- `render_to_string(view, *, url="/")` renders synchronously. Async memos don't start on the server in this mode; their `Loading` boundaries render fallbacks, and the client loads the data after hydration.
- `render_to_string_async(view, *, url="/", timeout=30)` resolves every async memo read during rendering (including waterfalls, where one async result decides what renders next), then renders the final HTML and appends the serialized state.
- `render_to_stream(view, *, url="/", timeout=30)` yields the shell immediately, with fallbacks for pending boundaries, then yields one chunk per `Loading` boundary as its content becomes ready (out-of-order streaming), and finally the serialized state. Every chunk belongs inside the mount container.
- `hydrate(view, container)` adopts the server-rendered DOM under `container` and returns a `Root`, like `render`.
- `is_server()` reports whether the current code is running inside a server render.
- `client_only(children, *, fallback=None)` renders `fallback` on the server and during hydration, then swaps in `children` once hydration has finished. Use it for widgets that need browser APIs.
- `create_memo(..., ssr_source="server" | "hybrid" | "client")` chooses where an async memo resolves; see "Async data".

The strings returned by the server functions are the *contents* of the mount container. The caller supplies the surrounding document.

### How the server renders

The server runs the ordinary reconciler against a new `ServerBackend`. That's a small in-memory DOM that implements the kernel wire protocol and serializes to HTML. Using the real reconciler, rather than a separate string renderer, guarantees that the server produces exactly the node structure the client expects: `Loading` parking, `Errored` fallbacks, list regions, holes, and fragments all behave identically by construction. The server backend doesn't parse templates, so every element takes the per-node mount path, which is also the path hydration uses.

Node ids are process-global, so concurrent renders in one asyncio process can share the backend: each render mounts into its own detached container, and the ids never collide. Rendering is synchronous within each pass, so the reactive core's module-level scope variables are never left set across an `await`.

Server mode changes a few runtime behaviors, matching Solid:

- `create_effect`, `create_tracked_effect`, and `on_settled` don't run. Render effects (holes and prop bindings) run once, as they do during any mount. Framework-internal effects, such as the one that switches a `Loading` boundary between content and fallback, still run.
- The router reads the request URL instead of `window.location`, and `navigate` is a no-op.
- `Portal` renders nothing; its content mounts in the browser after hydration.
- `create_unique_id` produces ids that match between the server and the hydrating client.

### Async data

A *hydration session* is active during a server render pass and during `hydrate`'s initial mount. The session gives every memo, `Loading` boundary, `Errored` boundary, and unique id created during the mount a key derived from its *position*: each component, hole, list row, and branch knows its place in the rendered tree, and a counter within that place numbers what's created there. A position doesn't depend on when async data arrives, so a key identifies the same memo in every server pass and in the browser. Each serialized value also records the qualified name of the function that computed it, and a value is only applied to a memo with the same function.

`render_to_string_async` resolves data in passes. Each pass renders the whole tree with every value resolved so far, starts the async memos that aren't resolved yet, and waits for them. Rendering again after new values arrive discovers the next level of a waterfall (data that only renders once earlier data exists). Work still running when a pass ends carries over to the next pass instead of starting again. The final pass has every value available, so it renders synchronously from start to finish, which is exactly what the client does during hydration. Its values are serialized as JSON in a `<script type="application/json" data-wyb-state>` element at the end of the container.

Rejections are serialized too, and the client raises them as [`ServerError`][wybthon.ServerError], which carries the original type name and message. `Errored` boundaries that show their fallback on the server are recorded in the state as well, so the hydrating client starts them on the fallback and claims the markup the server sent instead of rendering content that would immediately fail.

On the client, a memo whose key has a serialized value starts with that value instead of raising `NotReadyError`:

- If the memo's function is synchronous and *returns* an awaitable (`create_memo(lambda: fetch_user(user_id()))`), the function runs so its dependencies are tracked, and the coroutine it returns is closed without running. Nothing is fetched twice.
- If the memo's function is itself an `async def`, its dependencies are only discoverable by running it, so it reruns quietly in the background after hydration: no fallback, no pending state, and the server value stays on screen until the new one lands. Prefer the first form for data the server has already fetched.

`ssr_source` controls this per memo:

| Value | On the server | While hydrating |
| --- | --- | --- |
| `"server"` (default) | Resolved and serialized | Uses the serialized value |
| `"hybrid"` | Resolved and serialized | Uses the serialized value, then always reruns quietly |
| `"client"` | Never runs; reads are pending | Runs normally |

Serialized values must be JSON-compatible. A value that isn't is skipped with a dev-mode warning, and the client loads it itself.

### Streaming

`render_to_stream` runs the same passes but emits as it goes, and it starts the next pass as soon as any pending work settles rather than waiting for all of it, so a fast boundary never waits for a slow one. The first pass is sent as the shell. `Loading` boundaries write their start and end markers as comments carrying the boundary's key (`<!--wyb:b3f9c...-->` and `<!--/wyb:b3f9c...-->`). After each later pass, every boundary that's present in the streamed document, was showing its fallback, and now shows its content is sent as a `<template>` holding the boundary's new inner HTML plus a one-line script that swaps it in between the markers. Nested boundaries arrive in later chunks. `Reveal` ordering is respected automatically, because each pass computes each boundary's display mode with the same `Reveal` logic the client uses.

### Hydration

Hydration reuses the mount code in a *claim* mode. Instead of creating a node and inserting it, the reconciler emits claim operations that take the next node in each parent's child list:

| Op | Arguments | Meaning |
| --- | --- | --- |
| `HYDRATE` | root | Start claiming under `root` |
| `CLAIM_ELEMENT` | id, parent, tag | Claim the next element |
| `CLAIM_TEXT` | id, parent, text | Claim the next text node, splitting merged text |
| `CLAIM_COMMENT` | id, parent, data | Claim the next comment marker |
| `HYDRATE_END` | none | Remove unclaimed server nodes and stop claiming |

The kernel keeps one cursor per parent. The HTML parser merges adjacent text nodes and drops empty ones, so a text claim splits a longer server text node when it starts with the expected text and creates an empty text node when the expected text is empty. Whitespace-only text between elements is skipped.

Claims are tolerant. If the next node doesn't match, the kernel creates the expected node in place, warns once in dev mode, and continues; `HYDRATE_END` removes any server nodes that were never claimed. An end marker that carries a boundary key resynchronizes by searching forward for its matching comment, so a mismatch inside a `Loading` boundary doesn't cascade past it. A mismatch therefore costs extra DOM work, never a broken page.

Attribute, property, and style operations are still emitted during hydration. They're idempotent on matching nodes, and they make a node created by a mismatch correct. Event handlers and refs attach as usual. The whole initial mount remains a single bridge crossing.

Hydration only claims during the synchronous initial mount. `Portal` content, lists and holes that update later, and anything an effect mounts use the normal create path.

### The boot pipeline

- **Entry points return views.** `entry` in `wybthon.toml` now names a function that returns the root view, and the new `mount` key names the container (default `"#app"`). The bootstrap calls `hydrate` when the container holds server-rendered state and `render` otherwise. The same entry point drives prerendering.
- **Prerendering.** `prerender = ["/", "/about"]` in `wybthon.toml` makes `wyb build` render each listed route with `render_to_string_async` in a subprocess and write it to `<route>/index.html`. `crawl = true` also follows the in-app links each rendered page contains. The template marks the region to replace with `<!-- wyb:app -->` and `<!-- /wyb:app -->`. The client-only shell is written to `200.html`, which `wyb preview` and `wyb dev` serve for routes that weren't prerendered. `wyb dev` prerenders the same routes on every rebuild. The starter project prerenders `/` and crawls from there.
- **Precompiled bytecode.** When the build interpreter's version matches the pinned Pyodide's Python version, the runtime and application archives include unchecked-hash `.pyc` files (PEP 552) under `__pycache__`, so the browser skips compiling Wybthon and the application at startup. `bytecode = false` opts out, and the manifest records whether bytecode shipped. Server-only modules (`server.py`, `_server_dom.py`, `_prerender.py`, and the build tools) are no longer shipped to the browser.
- **Early input replay.** The bootstrap records clicks, input, changes, and form submissions that happen before hydration, prevents submissions from navigating, and replays them through the delegated event system once the page is hydrated. Input values typed before hydration are restored before their events replay.

### SolidJS 2.0 RC parity sweep

- `flush(fn)` runs `fn` and flushes synchronously, returning `fn`'s result.
- `create_signal(..., owned_write=True)` allows writes from inside an owned scope, Solid's narrow escape hatch from the dev-mode write guard. It covers both the value and function forms.
- `create_owner()` and `is_disposed(owner)` join `create_root`.
- Reading an accessor at the top level of a `For`, `Show`, or `Match` callback body warns in dev mode, as it already does for component bodies.
- The `Dynamic` control-flow component is removed; `dynamic(source)` replaces it, as in Solid.

### Clearing lists

Replacing a list with an empty one (or clearing a store list) now disposes every row's reactive resources and emits one range removal and one release, instead of computing row matches and removing each row separately. The JavaScript kernel performs every range removal as a single native `Range.deleteContents()`. Clearing 1,000 rows makes about 13% fewer Python calls and took up to 27% less time in noisy native benchmark runs; cleanup order is unchanged.

## Breaking changes

- `entry` in `wybthon.toml` must return the root view instead of calling `render`. Add `mount` if the container isn't `#app`.
- The default `index.html` wraps its loading indicator in `<!-- wyb:app -->` and `<!-- /wyb:app -->` markers. Templates without the markers still work for client-only builds but can't be prerendered.
- `Dynamic` and `DynamicComponent` are removed. Use `dynamic(source)(*children, **props)`.
- `create_unique_id` returns `wyb-h` followed by a short hash of the component's position inside a hydration session, and `wyb-<n>` otherwise.
- `wyb preview` and `wyb dev` fall back to `200.html` instead of `index.html` for unknown routes; configure static hosts the same way.
- The runtime archive no longer contains `wybthon.server`, `wybthon.build`, `wybthon.dev`, or the mypy plugin.
- The kernel wire protocol gains opcodes 22 through 26 (`HYDRATE`, `CLAIM_ELEMENT`, `CLAIM_TEXT`, `CLAIM_COMMENT`, and `HYDRATE_END`), and `CREATE_COMMENT` takes optional comment data.

## Alternatives considered

- **A separate string renderer on the server.** It would be faster per request, but it would duplicate the semantics of `Loading`, `Errored`, lists, and holes, and every divergence would be a hydration mismatch. Rendering through the real reconciler makes the output correct by construction. A direct string emitter remains possible later as an optimization behind the same API.
- **Render-and-swap instead of claiming.** Rendering a fresh tree off-screen and swapping it in at the end is simpler and can't mismatch, but it discards focus, selection, scroll positions, and typed input, and it restarts media and CSS animations. Claiming preserves them.
- **Dense template claiming.** Claiming whole template skeletons with one pre-order walk would send fewer ops, but hole content and component output are interleaved with the skeleton in the server DOM, so the pre-order ids don't line up. Per-node claims are simpler and still cross the bridge once.
- **Creation-order keys.** Numbering memos in the order they're created is simpler, and it's deterministic within the final pass. But between passes it isn't: when an async value arrives, the content it reveals creates memos in the middle of the order, shifting every later key, so a value resolved in one pass would seed the wrong memo in the next. Position keys don't shift. The function-name check guards against the remaining cases, where different content renders at the same position.
- **Waiting for all data between streaming passes.** It needs fewer passes, but a single slow request would hold back every boundary. The string renderer waits for everything; the stream advances on the first result.
- **Speeding up the renderer instead.** A leaner binding node and call-site template caching could cut mount time by an estimated 30% to 40%. That's worth doing, but it doesn't change the 1.8 s the page spends waiting for Pyodide. It stays on the list for a later RFC.
- **Do nothing.** Every Wybthon app would keep a blank page while Pyodide boots.

## Drawbacks and risks

- **Server throughput.** Rendering through the backend costs more per request than concatenating strings. It's adequate for prerendering and modest request rates; a direct emitter can replace it later.
- **Multiple passes.** Async rendering renders the tree once per level of data dependency. Apps rarely have more than two or three levels, and each pass is synchronous Python.
- **Determinism.** Hydration assumes the client's initial render matches the server's final pass. Code that reads the clock, random numbers, or browser-only state during render produces mismatches. They heal, but they cost DOM work; `client_only` and `is_server` are the tools for avoiding them.
- **Server-incompatible code.** Application code that imports `js` or `pyodide` at module scope can't be prerendered. The prerender step reports the import error with advice to guard it with `is_server()`.

## Testing

- `tests/test_ssr.py` renders views on the server backend, parses the HTML into the stub DOM, hydrates it through the reference `PythonBackend`, and asserts that no element was created, that there were no mismatches, and that events and reactive updates work afterward. The cases cover text merging, empty text, holes, fragments, lists, `Show`, `Switch`, `Loading`, `Errored`, portals, the router, lazy components, unique ids, and `client_only`. It also covers async resolution across waterfalls, serialized errors, every `ssr_source`, `async def` memos, non-JSON values, timeouts, streaming chunk order (including nested boundaries and `Reveal`), the equivalence of the streamed document and the async render, resynchronization at `Loading` end markers, recovery from deliberately mismatched HTML, and event replay.
- `tests/test_parity.py` covers `flush(fn)`, `owned_write`, `create_owner`, `is_disposed`, the callback read warnings, the list clear path (one range removal, unchanged cleanup order), prerendering, crawling, the `200.html` shell, bytecode that imports without its source, and configuration validation.
- `tests/e2e/test_hydration.py` builds a prerendered app, loads it in Chromium, checks that the server HTML shows while Pyodide is still loading, clicks and types before hydration, and verifies that the input replays, that the server's data isn't fetched again, and that hydration reports no mismatches.
- All 572 unit tests and all 63 browser tests pass, as do Ruff, Black, mypy, and the strict documentation build. Python call counts for creating 1,000 rows are unchanged (179,099 versus 179,100 on the baseline).

## Unresolved questions

- Derived and projected stores (`create_store(fn)`, `create_projection`) with async bodies aren't serialized yet; they load on the client after hydration.
- Server functions (Solid's `"use server"`) and HTTP status and header control are left for a later RFC.
- A native-code or string-emitting server renderer, and a leaner client binding node, are candidates for a performance RFC.

## Decision

Accepted on 2026-09-29, with implementation requested in the same change.

## Implementation

Implemented in [#38](https://github.com/wybthon/wybthon/pull/38).
