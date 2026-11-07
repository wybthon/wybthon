# RFC 0008: Full-stack apps: server functions, the router's data layer, and a smaller first visit

- **Status:** Implemented
- **Author:** Owen Carey
- **Created:** 2026-11-07

## Summary

Make a Wybthon app one Python codebase for the browser and the server, as Solid 2.0's start mode makes a Solid app one codebase. Seven engine releases brought rendering close to what Python can do; what's missing is everything Solid 2.0 moved into its core around rendering, and what a first visit costs before any of it runs. This RFC adds:

1. **Server functions.** `@server_function` makes an `async def` run on the server wherever it's called, as `"use server"` does. The build removes its body, and the imports only it used, from the browser's copy, and arguments are validated against the function's annotations.
2. **The router's data layer, as in Solid Router 2.0.** `query`, `revalidate`, `form_action` (with `.bind`, `on_submit`, and `on_settled`), and `use_submissions`; responses with `redirect`, `reload`, and `respond`.
3. **A Router 2.0 router.** `create_router(routes)` replaces the `Router` component, plain `<a>` links replace `Link`, a root layout replaces wrapping the router, and links preload on hover.
4. **A server.** `wybthon.asgi` renders pages per request and serves server functions, JavaScript-free form posts, HTTP handlers, and assets; `wyb serve` runs it, and `wyb dev` serves `server = true` projects through it.
5. **File routes.** `file_routes("app.routes")` turns a package of modules into the route tree, with layouts, groups, parameters, and catch-alls.
6. **Pages that work before Python boots.** A form posting to a server function submits natively until the page has hydrated; the server redirects back with the result in a flash cookie.
7. **A trimmed standard library.** The build ships the standard library modules the app can import, about 1 MB of Pyodide's 2.5 MB, and fetches the rest only if an import needs it.

It also fixes wybthon/wybthon#44 and wybthon/wybthon#46.

## Motivation

### Rendering is close to the ceiling

Creating 1,000 benchmark rows takes 4.3 ms of CPython (about 61 calls per row), and 15.6 ms in the browser in store mode. Updating, selecting, and swapping rows cost almost nothing. Solid's script time for the same rows is a few milliseconds, and the browser's own layout and paint cost more than either. Another engine pass might take creating and clearing rows 1.3 to 2 times faster, at the price of more fast paths in a 3,600-line core, for an improvement few pages would show.

### A first visit is what users wait for

[Engine v6](0006-engine-v6.md) made repeat visits start in about 100 ms. A first visit still downloads Pyodide's WebAssembly (3.4 MB with Brotli), its standard library (2.5 MB, already compressed), and Wybthon's runtime (0.74 MB), then spends most of a second starting Python. The renderer can't change that. Two things can: downloading less, and a page that's useful before Python has started. Server rendering already shows the page; until now, nothing on it worked before hydration, since a form submitted early was held and replayed.

### Solid 2.0 moved the full stack into its core

Solid 2.0 is still a release candidate: npm's `latest` is `solid-js@1.9.18`, and `next` is `2.0.0-rc.21`. The changes queued for RC.22 are fixes. But Solid 2.0 made `"use server"` a core feature (`@solidjs/web/server-functions`), its Vite plugin's start mode replaces SolidStart, and Router 2.0 (`2.0.0-next.44`) rebuilt the data layer around it: `query`, `revalidate`, `formAction`, `useSubmissions`, `createRouter({ routes })`, and plain `<a>` links. Wybthon had a basic router and a server renderer applications had to wire into their own server. For Python this matters more than for JavaScript: the same language on both ends is the strongest reason to choose Wybthon, and nothing let an app use it.

## Design

### 1. Server functions

`server_function(fn)` (or `server_function(method="GET")(fn)`) returns a `ServerFunction` whose id is `module:qualname`; the function must be a module-level `async def`, so the browser and the server name it the same way.

- **On the server**, a call runs the function. A `redirect` it raises while a page renders becomes the page's response.
- **In the browser** (`sys.platform == "emscripten"`, or with a test transport), a call posts `{"args": [...], "kwargs": {...}}` to `{base}_wyb/fn/{id}` (a GET sends it in the query string) with an `x-wyb-fn` header, and decodes `{"ok": value}`, `{"error": {...}}`, or `{"redirect": url}`, with optional `revalidate` keys.
- **The wire format** (`wybthon._wire`) is JSON plus tagged dataclasses, enums, tuples, sets, frozensets, non-string-keyed dicts, dates and times, `timedelta`, `Decimal`, `UUID`, and `bytes`. Decoding what the server sent rebuilds dataclasses and enums whose modules are already imported, without importing anything or calling `__init__`. Decoding what a browser sent ignores class tags, and `_wire.coerce` rebuilds each argument from the function's annotations, rejecting anything else with a 400. Server-rendered state uses the same format, so a dataclass a query returns no longer has to be fetched again after hydration, and it's decoded when its memo takes it, after a lazily loaded route has imported its module.
- **Errors** arrive as `ServerError` with the exception's type name. An unexpected exception's message (and traceback) is sent only in development.
- **Mutations revalidate.** A completed POST call revalidates every query on the page unless its response named keys (`respond(value, revalidate=[...])`, with `""` meaning none). A redirect from a POST navigates and completes, so the action around it settles and reveals the navigation; a redirect from a GET leaves the read pending while the page leaves.
- **Requests.** The ASGI app sets a context variable for the request, so `get_request_event()` works in server functions and in async work a render starts. `RequestEvent` gains `method`, `headers`, and `cookies`, and `set_cookie` writes a `set-cookie` header.
- **Cross-site requests.** A call without the header must be a form post from the same origin (`Sec-Fetch-Site`, or `Origin` against `Host`).

**What reaches the browser.** `wybthon._split` edits each application module's source before it goes into a browser archive: the body of every function decorated with `server_function` becomes `...`, a file route's HTTP handlers likewise, and a top-level import whose names only those bodies used becomes `pass`. The edit is textual and keeps every line in place. Modules matching `server-only` globs aren't shipped. `wyb dev`'s hot updates send the same edited source. A build that finds server functions without `server = true` fails.

### 2. The data layer

- **`query(fn, key)`** returns a `Query`; `@query` and `@query("key")` work as decorators, and the key defaults to the server function's id. A call reads a version signal for its full key (the key plus its encoded arguments), so the calling memo depends on it, and returns a coroutine that starts the fetch only when awaited, so hydration, which discards the coroutine of a memo the server already resolved, fetches nothing. Results are shared while pending and reused for five seconds after they arrive; failures aren't cached. On the server, calls are deduplicated per request. A `ServerFunction` wrapped in a query is called with GET.
- **`revalidate(keys)`** drops matching cache entries and bumps the matching version signals, so each memo that read one runs again (holding its value meanwhile, as any async memo does). Keys match by prefix; a `Query` stands for its key.
- **`form_action(fn, name)`** returns a `FormAction` wrapping an `Action`. Its `__str__` is its URL, so `action={add_todo}` renders a real `action` attribute; rendering it also installs the submit handling. `bind(*args)` returns an action whose URL carries the arguments. `on_submit` and `on_settled` hooks belong to the calling owner. A client-only action needs a name and revalidates everything when it completes.
- **Submissions.** A settled submission (`input`, `result`, `error`, `url`, `clear()`, `retry()`) joins the action's history, capped at 32; `use_submissions(action, where)` reads it.

### 3. The router

`create_router(routes, *, base="", preload_links=True)` returns a `Router`; `router(root=Shell)` renders it with a root layout. Routes match as in Router 2.0: child paths continue the parent's path even when they start with `/`, a route with children matches only through one, `*name` catch-alls and `:name?` optional parameters join `:name`, and literals outrank parameters, which outrank catch-alls. No match renders nothing and sets a 404 on the server. Route components receive `params`, `search`, `data` (the resolved `preload` result), and `children`. `preload` receives `PreloadArgs` with an `intent`.

**Plain links.** A new kernel command, `INTERCEPT`, makes the kernel's root listener for an event type dispatch even when no handler is on the route, with a payload describing the link (`href`, resolved `url`, `target`, `download`, `rel`, `preload`, same-origin) or the form (`action`, `method`, its node id). `events.intercept(type, handler)` registers default handling that runs after the delegated handlers unless one prevented the event. The router intercepts `click` (navigate), and `pointerover` and `focusin` (preload, once per link the pointer reaches); form actions intercept `submit`. The test backend reports the same payloads from its stub DOM.

**Reading the URL.** `use_params`, `use_search_params` (with a merging setter), `use_location`, `use_route_matches`, `use_link_state`, and `preload_route` replace `current_path`, `use_query`, `use_hash`, `use_base_path`, `preload`, and `Link`'s active class.

### 4. The server

`wybthon.asgi.App` reads a server build, imports the entry and every module that defines server functions (found by scanning sources, so a request never chooses what's imported), and answers:

- `{base}_wyb/fn/{id}`: a server function. A form post without the header (a browser with no Python yet) gets a 303 to the action's redirect or the same-origin `Referer`, and a 30-second `wyb_flash` cookie carrying the submission, which `use_submissions` reads on the server and, once, in the browser.
- A file route's HTTP handler, for its method, except a page load (`GET` accepting `text/html`) of a route that also has a page.
- A file in the build (content-hashed assets cached for a year), or a prerendered route's HTML.
- Otherwise, the page: `render_to_stream` into the build's `200.html` shell, through middleware, which can change the status and headers because the response is created once the shell has rendered.

**The shell waits for unbounded reads.** A stream used to send its shell on the first pass. It now waits until no async read outside every `Loading` boundary is in flight (a boundary sets the loading context its reads find), since the shell is what's outside boundaries. A guard query that redirects therefore becomes the HTTP redirect; one that redirects after the head was sent is followed by a script at the end of the stream.

`wybthon._http` is a small asyncio HTTP/1.1 server (keep-alive, chunked responses, `HEAD`) for `wyb serve` and `wyb dev`. In server mode, `wyb dev` serves through `App`, injects its reload script into pages, re-imports the application's modules after each rebuild, and keeps hot updates.

### 5. File routes

`file_routes(package)` scans the package directory: `index.py` is the directory's path, `[id].py` a parameter, `[[id]].py` an optional one, `[...rest].py` a catch-all, `(group)/` adds no segment, `_layout.py` (a `Layout` component) wraps its directory, and other `_` files are private. A module is a page when its source defines `Page`, found by a cheap text scan so nothing is imported up front; pages load through `lazy`. Module names that aren't identifiers are imported by path under stand-in names (`[id]` is `_wyb__5b_id_5d_`) through Wybthon's compiling loader, since `importlib` splits names on dots. `api_routes(package)` lists the HTTP handlers the same way.

### 6. Forms before Python

The bootstrap records input before hydration and replays it; it used to hold every form submit. A submit whose action (or submitter's `formaction`) posts to `/_wyb/fn/` is now left to the browser, so the server handles it as described above.

### 7. The standard library

`wybthon._stdlib.trim` splits Pyodide's `python_stdlib.zip` into the modules to ship and the rest. It keeps every module Pyodide 314 was measured importing to boot a Wybthon app, `_pyodide` and `pyodide` whole (Pyodide imports their submodules from C before Python code can intervene), a handful of codecs, the modules Wybthon's browser modules and the application import, and the closure of those. Only module-level imports count: imports in functions, under `TYPE_CHECKING`, and behind `if __name__ == "__main__"` don't, which keeps `heapq`'s doctest import from pulling in `doctest`, `pdb`, and `unittest`. Data files stay with the library.

The page passes the trimmed library to `loadPyodide({stdLibURL})`, in the page and in the snapshot worker, and installs `wybthon._stdlib_rest`, the last finder on `sys.meta_path`, before the application imports. When an import misses a module the manifest's index of the rest lists (whole top-level names, and `package.*` for packages split between the two), the finder fetches the rest synchronously, once, mounts it as a zip, extends the `__path__` of standard library packages already imported, and lets the import continue. The index matters: `hashlib` tries `_hashlib`, which Pyodide lacks, and an unindexed miss would have fetched the rest at every boot.

The build downloads the library once per Pyodide URL and caches it. With `stdlib = "full"`, without network access, or with `packages` or `wheels` (whose imports it can't see), it ships Pyodide's library. The snapshot key includes the trimmed library.

### 8. Fixes

- wybthon/wybthon#46: `_event_loop` uses `asyncio.get_event_loop()` instead of the deprecated policy API.
- wybthon/wybthon#44: the pytest plugin skips modules in the `wybthon` package next to it, so installing from a wheel no longer compiles the compiler while it imports.
- `testing.py` no longer ships to the browser.

## Results

Measured on an Apple M-series laptop with Chromium and Pyodide 314.0.6.

| First-visit download | v0.42.1 | This RFC |
| --- | ---: | ---: |
| Pyodide WebAssembly (Brotli) | 3.44 MB | 3.44 MB |
| Standard library | 2.55 MB | 0.97 MB |
| Wybthon runtime archive | 0.74 MB | 0.83 MB |
| Total | 6.73 MB | 5.24 MB (-22%) |

The runtime archive grows by the router package, server functions, and the wire format, less the test renderer. The trimmed library is the same for both starters, because Wybthon's own imports dominate its roots. A page that never imports outside it never fetches the 1.6 MB rest. Rendering is unchanged: the native row benchmark creates 1,000 rows in 4.3 ms, as before.

In Chromium, the full-stack starter renders on the server, hydrates without mismatches, runs its form as an action and as a JavaScript-free post, navigates through plain links without loading a page, and restores a snapshot of the trimmed runtime, which a repeat visit was ready in under 200 ms in a sample run.

## Breaking changes

| Removed or changed | Replacement |
| --- | --- |
| `Router(routes, base_path=..., not_found=...)` | `router = create_router(routes, base=...)`, rendered with `router()` or `router(root=Layout)`; a `Route("*404", NotFound)` for not found |
| `Link(...)` | A plain `<a href>`; `use_link_state(href)` for active styling |
| `current_path` | `use_location()`, or `wybthon.router.url` |
| `use_query()`, `QueryParams` | `use_search_params()`, `SearchParams` |
| `use_hash()`, `use_base_path()` | `use_location().hash`; the router's base is `router.base` |
| `preload(path)` | `preload_route(path)` |
| `RouteProps.query` | `RouteProps.search`; `data` and `children` are new |
| `Route.preload(params)` | `Route.preload(PreloadArgs)` |
| A child path starting with `/` was absolute | Child paths always continue the parent's |
| A route with children matched on its own | It matches through a child: add `Route("/")` |
| No match rendered "Not Found" | No match renders nothing (a 404 on the server) |
| `wybthon.router` was a module | A package |
| Server-rendered state was JSON | The wire format; values JSON couldn't hold now arrive |
| A stream sent its shell on the first pass | It waits for async reads outside `Loading` boundaries |
| The bootstrap held every pre-hydration submit | Submits to server functions post natively |
| `SET_ATTR` on a released node raised | It's ignored |
| The browser runtime included `wybthon.testing` | It's server-side only |
| Tests named by release (`test_rc17.py`, `test_rc21.py`, `test_engine_v5.py`) | Named by what they cover |

## Alternatives considered

**Another rendering pass.** See the motivation: little left to win where users wait.

**A native reactive core.** Rust compiled to WebAssembly would speed up graph bookkeeping, which isn't what first visits wait on, and needs a wheel per Pyodide ABI plus a pure-Python twin for tests.

**Hashed server function ids.** Solid hashes its ids. A readable `module:qualname` is easier to debug, and the server resolves ids only against functions it registered by scanning its own sources, so the name grants nothing.

**Trimming by tracing imports at run time.** Booting the app in a browser at build time would find dynamic imports too, but needs a browser for every build; the static closure plus a correct fallback costs one slow import at worst.

**Bracket-free file names.** `[id].py` isn't an identifier, and `[...rest].py` can't even be imported by name. Every Solid, Svelte, and Next user reads the bracket convention at a glance, so the router imports such modules by path instead.

**Adopting RC.22's context providers now.** RC.22 isn't published, and its change to providers alters the owner tree's shape; it waits for the release.

## Unresolved questions

- Single-flight mutations: a mutation's response carrying the refreshed data of the queries it revalidates.
- `liveQuery`, server components, and typed paths.
- Whether `wyb build` should ship a build-time snapshot for apps whose first visits matter most.
- Request bodies with chunked transfer encoding in `wybthon._http` (it answers 411).

## Testing

- The unit suite (1,133 tests), with new suites for server functions and the wire format, the source splitter, the router, the data layer, file routes, the ASGI app (through `wybthon.testing.Client`), the HTTP server, standard library trimming, and the two issues.
- The browser suite (94 tests), with the fixture app on the new router and a new full-stack suite: `wyb serve --build` and `wyb dev` on the server starter, JavaScript on and off.

## Decision

Accepted on 2026-11-07. Wybthon is pre-1.0 and has no production users yet, so the changes ship without a compatibility layer.
