# Deployment

`wyb build` creates an application bundle from a project containing `wybthon.toml`. A static project's bundle goes on any static host, and `wyb preview` serves it with client-route fallback and the configured base path. A project with `server = true` is served by Python, which renders pages per request and runs server functions (see [Serving a full-stack app](#serving-a-full-stack-app)).

```toml
entry = "app.main:app"
mount = "#app"
app-dir = "app"
base = "/"
pyodide-version = "314.0.6"
packages = []
wheels = []
prerender = ["/"]
crawl = true

[chunks]
charts = ["app/charts/**"]
```

The entry function returns the root view (it can be async); the bootstrap renders it into `mount`, or hydrates it when the page was prerendered. Projects require Python 3.14, matching the Pyodide 314 runtime. `index.html` must contain exactly one `<!-- wyb:bootstrap -->` marker. Files in `public/` are copied beside the output HTML; `public/assets/` is reserved for generated content.

```bash
wyb build --base /dashboard/
wyb preview --dir dist --port 8000
```

Deploy the contents of `dist/`, configure missing extensionless routes to serve `200.html`, and serve the app beneath `/dashboard/` in this example. Use long-lived immutable caching for hashed assets and revalidate the HTML files and `manifest.json`. The preview server demonstrates that policy; use your static host for production serving.

## Serving a full-stack app

With `server = true`, the build also records `"server": true` in its manifest, and [`wybthon.asgi`][wybthon.asgi] serves it:

```bash
wyb build
wyb serve --port 8000
```

`wyb serve` uses Wybthon's small built-in HTTP server, which is fine behind a reverse proxy. For production traffic, run the same ASGI app under an ASGI server such as uvicorn or hypercorn, from the project directory (or with `WYBTHON_PROJECT` pointing at it):

```bash
WYBTHON_PROJECT=/srv/my-app uvicorn --factory wybthon.asgi:create_app --workers 4
```

The app serves the build's assets itself, with a year of immutable caching for content-hashed files, so a CDN in front of it can cache them. It imports the application in-process (with `is_server()` true while it does), so the server needs the app's server-side dependencies installed: everything `server-only` modules and server functions import. Routes listed under `prerender` are served from their prerendered HTML; every other page is rendered per request. See [Full-stack apps](../concepts/full-stack.md#serving) for middleware and HTTP handlers.

Server functions are public endpoints: authorize every call that needs it, and keep secrets in the server's environment, never in a module the browser gets. The build strips server function bodies, HTTP handlers, the imports only they use, and `server-only` modules from the browser's archive; everything else in the app directory is public.

## What the page loads

The build replaces the `<!-- wyb:bootstrap -->` marker with the tags that start the application, so every page it writes (`index.html`, `200.html`, and each prerendered route) carries them:

- A `<link rel="modulepreload">` for Pyodide's `pyodide.mjs`, and a `<link rel="preload" as="fetch" crossorigin>` for the runtime archive, the application archive, and the trimmed standard library. The browser starts downloading them while the page parses, instead of after the bootstrap has run.
- The manifest, inlined as `<script type="application/json" id="wyb-manifest">`, so the bootstrap doesn't spend a round trip fetching it. `manifest.json` is still written at the root of the output, and the bootstrap falls back to fetching it when a page doesn't carry the inline copy.
- The bootstrap module itself.

## Production mode

`wyb build` writes a production build: the bootstrap calls [`set_dev_mode(False)`][wybthon.set_dev_mode] before the application imports, so production apps skip the development checks (such as unknown-prop validation and write-in-scope errors) and print no development warnings. The manifest's `dev` field records the mode. `wyb dev` builds the same project with dev mode on. From Python, [`build_app`][wybthon.build.build_app] builds for production by default; pass `dev=True` for a development build. Read the current mode with [`is_dev_mode()`][wybthon.is_dev_mode].

## Reproducible output

Builds sort files and normalize archive timestamps, so identical inputs produce identical assets. A complete build is prepared before the destination is replaced. Existing nonempty output must contain the `.wyb-build` marker; source directories can't be used as output. Build validation failure leaves the previous output available.

## Prerendering

`prerender` lists routes to render to HTML at build time, and `crawl = true` adds every in-app link those pages contain. Each route is written to `<route>/index.html` with the markup placed between the `<!-- wyb:app -->` and `<!-- /wyb:app -->` markers in `index.html`. The browser shows the page immediately and [hydrates](../concepts/server-rendering.md) it once Pyodide is ready. Prerendering imports the application in a separate CPython process, after Wybthon, so the import hook compiles its templates; browser-only imports must be guarded there, and the build reports the failing import otherwise. `wyb dev` prerenders the same routes on every rebuild.

The client-only shell is also written to `200.html`. Serve it for routes that weren't prerendered.

## Compiled templates

`wyb build` runs every application module through Wybthon's [compiler](../concepts/compiler.md) before packaging it. A malformed template fails the build with its file and line. Each `html(t"...")` call gets its dynamic expressions wrapped in getters and its parse tree and mount function emitted as ordinary module code, so a production page never parses a template or generates code at run time.

## Bytecode

When the interpreter running the build has the same Python version as the pinned Pyodide runtime (Python 3.14 for Pyodide 314), the archives include precompiled bytecode, so the browser doesn't compile Wybthon or the application at startup. Application bytecode is the compiler's output, and the import hook that `import wybthon` installs uses it as is. The manifest's `bytecode` field records whether it was included. Set `bytecode = false` to ship source only; the import hook then compiles each application module's templates in the browser as it's imported.

## A trimmed standard library

Pyodide's standard library archive is 2.5 MB, and a first visit downloads all of it, though an app imports a fraction. `wyb build` trims it: it ships the modules Pyodide imports to boot, the modules Wybthon and the application import when they're imported, and everything those import in turn, which for the server starter is under 1 MB. The page loads that instead of Pyodide's (`loadPyodide({stdLibURL})`).

The rest of the library is written beside it, with an index in the manifest. If the app imports a standard library module the build left out (inside a function that runs later, or by name at run time), the import fetches the rest, synchronously and once, and continues. Trimming never breaks an app; it can only make that one import slower. The console notes when it happens: move that import to module level, and the next build keeps the module.

The build downloads Pyodide's library once (from `pyodide-url`) and caches it. Without network access, or with `stdlib = "full"` in `wybthon.toml`, it ships Pyodide's library as is, as it does for builds with `packages` or `wheels`, whose imports it can't see. The manifest's `stdlib` field names the trimmed library, or is `null`.

## Boot snapshots

Most of a page's startup is Pyodide's: starting Python and importing the framework takes most of a second before the application runs at all. Builds avoid that work on every visit after the first. Once the first boot has finished and the page is idle, the bootstrap starts a Web Worker that boots a second runtime, imports Wybthon and the standard library modules applications commonly use, and takes a memory snapshot of it, which it stores in the browser's Cache Storage. Later visits restore that snapshot instead of starting Python, then unpack the archives and import the application as usual. In Chromium on a recent laptop, a repeat visit to the starter app is ready in about 100 ms instead of about 800 ms.

- **What's in it.** The runtime with the framework imported, not the application: application modules may read `window` when they're imported, which a snapshot can't hold. The snapshot is keyed by the Wybthon version, the runtime archive, and the Pyodide release, so it stays valid across application changes and every `wyb dev` reload restores it.
- **What it costs.** The first visit downloads nothing extra. Building the snapshot takes about a second of a background thread and stores about 30 MB in Cache Storage, replacing the app's older snapshot. Each app keeps its snapshots in a cache named by its base path, so apps sharing an origin don't evict each other's. A snapshot that can't be restored is discarded, and that boot falls back to starting Python normally. A build that fails (for example, because storage is full) isn't retried for a week.
- **When it's off.** Builds with Pyodide `packages` or `wheels` boot normally, since those live in the virtual file system rather than in memory. So does a page where Cache Storage or module workers aren't available (Cache Storage needs a secure context: HTTPS or `localhost`). Set `snapshot = false` in `wybthon.toml` to turn it off; the manifest's `snapshot` field is the key, or `null`.

`window.__WYB.timings.snapshot` says whether a boot restored a snapshot, and `window.__WYB.snapshot` reports one the page built (`built`, `bytes`, and `ms`, or an `error`). The page dispatches `wybthon:snapshot` on `window` when it's done.

## Runtime and dependencies

The bootstrap loads Pyodide and the runtime/application archives concurrently (the preload hints have usually started all three already), then unpacks and imports Python. It doesn't fetch every Python module separately. `packages` names packages in the pinned Pyodide distribution. `wheels` accepts exact `name==version` requirements or explicit wheel URLs compatible with the selected runtime. Set `pyodide-url` to host that runtime yourself.

Pin dependencies and keep the runtime version deliberate. Browser Python code is public, including bundled configuration. Keep application secrets on a server.

## Explicit lazy chunks

```python
from wybthon import lazy

Chart = lazy(lambda: ("app.charts.main", "Chart"), chunk="charts")
```

The matching files are excluded from the main archive. Rendering `Chart` inside `Loading` fetches its archive once before importing the module. The router preloads a lazy route's component when the pointer rests on a link to it, and `Chart.preload()` warms it on any user intent. `load_chunk("charts")` from `wybthon.assets` is available for explicit preloading.

Chunk groups mustn't overlap, and the entry module must stay in the main bundle. This is explicit packaging, not automatic dependency analysis: keep shared imports in the main application, and don't eagerly import a chunk module. Concurrent chunk requests share one fetch; a failed fetch is evicted so a later attempt can retry. Call `Chart.retry()` to restart a failed lazy load and let its error boundary recover.

## Startup measurements

`window.__WYB` exposes startup status, errors, the runtime, and timings for runtime loading, archive loading, unpacking, application startup, readiness, and the next frame opportunity. Concurrent phases overlap; don't add them as if they were sequential. These values include network/cache conditions and differ from warmed update benchmarks.

The production browser test builds a starter, boots a deep link beneath a base path, clicks a real counter, and verifies that its lazy chunk isn't fetched until requested.
