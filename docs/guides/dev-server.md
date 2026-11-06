# Dev server

`wyb dev` builds a Wybthon project in development mode, serves the build, and rebuilds when a source file changes. An edited application module is replaced in place in connected pages, without a reload; any other change reloads them. Both arrive over Server-Sent Events (SSE). It serves projects only: a directory with a `wybthon.toml` (create one with `wyb init`).

```bash
pip install wybthon
wyb init my-app
cd my-app
wyb dev --open
```

## Behavior

- Builds the project with dev mode on, including any routes listed in `prerender`, so you develop against the same server-rendered pages you'll deploy. Production builds (`wyb build`) turn dev mode off; see [Deployment](deployment.md).
- Runs application modules through Wybthon's [compiler](../concepts/compiler.md), as `wyb build` does, so a malformed template fails the rebuild with its file and line instead of failing in the browser.
- Serves the build under the configured `base` path with client-route fallback to `200.html`. Requests outside the base path return 404.
- Watches the application directory (`app-dir`), `public/`, `index.html`, and `wybthon.toml`. A change triggers a rebuild, then a hot update when only existing Python modules in the application directory changed, and a reload otherwise (a new or deleted file, a module in a lazy chunk, markup, assets, or configuration). Change detection polls modification times about every 0.5 seconds.
- Reports a failed build in the terminal and keeps serving the previous output, so a typo doesn't take the page down.
- Binds to the requested port or the next available one, up to 20 ports higher, and prints the project, the watched paths, and the URL it serves.
- Sends `Cache-Control: no-store` on every response, so the browser never reuses a stale build.

## Options

- `--dir`: the project directory (default `.`).
- `--host` (default `127.0.0.1`) and `--port` (default `8000`).
- `--open`: open the default browser to the app after the server starts.
- `--open-path`: open this path instead of the app's base path, for example `/about`.

To expose the server on your LAN or from a container, use `--host 0.0.0.0` and open the page via your machine's IP.

## Hot updates

Each page the dev build writes includes a small script that subscribes to `GET /__sse`. When a rebuild changed only Python modules that already existed in the application directory, the server sends an `hmr` event with their new sources, and the page replaces them in place ([RFC 0006](../rfcs/0006-engine-v6.md)):

1. The new sources are written into the runtime's file system, and each changed module that's been imported runs its new code in its existing namespace, through the compiler.
2. Components keep their identity: the existing `@component` object takes the new body, so modules that imported it render the new code. A plain function keeps its identity too, when the new code fits its closure.
3. Every mounted instance of a component from a changed module, or from a module that imported one, runs its body again in place with the same props. Only the outermost of nested instances remounts.

State that lives outside the remounted components (stores and signals in modules that didn't change, the router's location, everything else on the page) is kept. The remounted components' own local state starts over, as with Solid's hot reloading.

A module that hasn't been imported yet just gets its new source, and its build's bytecode is removed so the page imports the new code when it first needs the module. A change to a module in one of the `[chunks]` groups reloads the page, since the rebuild gives the chunk a new archive. A change that can't be applied in place reloads the page too: one that fails to compile or raises when it runs, a module that calls `render` when it's imported (return the root view from the entry function instead, as `wyb init` does), or a changed component that rendered nothing. `window.__WYB.hot` counts the hot updates a page has applied, and the page dispatches `wybthon:hot` on `window` after each one.

Other changes send a `reload` event, and pages reload. A reload restores the [boot snapshot](deployment.md#boot-snapshots) the first page load built, so it costs a fraction of a cold boot.

## Embedding the server

[`serve`][wybthon.dev.serve] is the function behind `wyb dev`:

```python
from wybthon.dev import serve

serve("my-app", host="127.0.0.1", port=8000, open_browser=True, open_path=None)
```

It raises `ValueError` when the directory has no `wybthon.toml`.

### Not for production

The dev server is built on Python's `http.server` and is intended for development only. Use `wyb build` and a static host for production, and `wyb preview` to check a production build locally. See the [Deployment guide](deployment.md).

## Troubleshooting

- **"has no wybthon.toml."** The dev server only serves projects. Run it from the project directory, pass `--dir path/to/project`, or create a project with `wyb init`. To try a single script with its templates compiled, use `wyb run script.py` instead.
- **Auto-reload isn't firing.** Confirm `GET /__sse` shows an open EventSource connection in the browser's Network panel, and check the terminal for a build error. Only the application directory, `public/`, `index.html`, and `wybthon.toml` are watched. Behind a proxy, pass `/__sse` through unbuffered (Nginx: `proxy_buffering off;` and `X-Accel-Buffering: no`).
- **A page shows 404.** Requests must fall under the configured `base` path. Open the URL the server prints.
- **Port is already in use.** The server picks the next free port and prints a notice. If you need the exact port, stop the conflicting process (macOS: `lsof -i :8000`, then `kill <PID>`).
- **The browser didn't open.** `--open` relies on the system default browser; some headless or remote setups block it. Copy the printed URL instead.
- **Exposing on the network.** Use `--host 0.0.0.0` and allow inbound traffic to the selected port through your firewall.

See also the general [troubleshooting page](../meta/troubleshooting.md).

## Next steps

- See the [`dev`][wybthon.dev] API reference for the underlying server.
- Read the [Deployment guide](deployment.md) for production builds and hosting.
- Browse [Examples](../examples.md) for components to try in a starter project.
