# Deployment

`wyb build` creates a static application bundle from a project containing `wybthon.toml`. `wyb preview` serves the result with client-route fallback and the configured base path.

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

The entry function returns the root view (it can be async); the bootstrap renders it into `mount`, or hydrates it when the page was prerendered. `index.html` must contain exactly one `<!-- wyb:bootstrap -->` marker. Files in `public/` are copied beside the output HTML; `public/assets/` is reserved for generated content.

```bash
wyb build --base /dashboard/
wyb preview --dir dist --port 8000
```

Deploy the contents of `dist/`, configure missing extensionless routes to serve `200.html`, and serve the app beneath `/dashboard/` in this example. Use long-lived immutable caching for hashed assets and revalidate the HTML files and `manifest.json`. The preview server demonstrates that policy; use your static host for production serving.

Builds sort files and normalize archive timestamps, so identical inputs produce identical assets. A complete build is prepared before the destination is replaced. Existing nonempty output must contain the `.wyb-build` marker; source directories can't be used as output. Build validation failure leaves the previous output available.

## Prerendering

`prerender` lists routes to render to HTML at build time, and `crawl = true` adds every in-app link those pages contain. Each route is written to `<route>/index.html` with the markup placed between the `<!-- wyb:app -->` and `<!-- /wyb:app -->` markers in `index.html`. The browser shows the page immediately and [hydrates](../concepts/server-rendering.md) it once Pyodide is ready. Prerendering imports the application in a separate CPython process, so browser-only imports must be guarded; the build reports the failing import otherwise. `wyb dev` prerenders the same routes on every rebuild.

The client-only shell is also written to `200.html`. Serve it for routes that weren't prerendered.

## Bytecode

When the interpreter running the build has the same Python version as the pinned Pyodide runtime (Python 3.14 for Pyodide 314), the archives include precompiled bytecode, so the browser doesn't compile Wybthon or the application at startup. The manifest's `bytecode` field records whether it was included. Set `bytecode = false` to ship source only.

## Runtime and dependencies

The bootstrap loads Pyodide and the runtime/application archives concurrently, then unpacks and imports Python. It doesn't fetch every Python module separately. `packages` names packages in the pinned Pyodide distribution. `wheels` accepts exact `name==version` requirements or explicit wheel URLs compatible with the selected runtime. Set `pyodide-url` to host that runtime yourself.

Pin dependencies and keep the runtime version deliberate. Browser Python code is public, including bundled configuration. Keep application secrets on a server.

## Explicit lazy chunks

```python
from wybthon import lazy

Chart = lazy(lambda: ("app.charts.main", "Chart"), chunk="charts")
```

The matching files are excluded from the main archive. Rendering `Chart` inside `Loading` fetches its archive once before importing the module. Hover preloading through a router `Link` can warm a lazy route. `load_chunk("charts")` is available for explicit preloading.

Chunk groups mustn't overlap, and the entry module must stay in the main bundle. This is explicit packaging, not automatic dependency analysis: keep shared imports in the main application, and don't eagerly import a chunk module. Concurrent chunk requests share one fetch; a failed fetch is evicted so a later attempt can retry. Call `Chart.retry()` to restart a failed lazy load and let its error boundary recover.

## Startup measurements

`window.__WYB` exposes startup status, errors, the runtime, and timings for runtime loading, archive loading, unpacking, application startup, readiness, and the next frame opportunity. Concurrent phases overlap; don't add them as if they were sequential. These values include network/cache conditions and differ from warmed update benchmarks.

The production browser test builds a starter, boots a deep link beneath a base path, clicks a real counter, and verifies that its lazy chunk isn't fetched until requested.
