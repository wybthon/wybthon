# Dev server

`wyb dev` builds a Wybthon project in development mode, serves the build, rebuilds when a source file changes, and reloads connected pages over Server-Sent Events (SSE). It serves projects only: a directory with a `wybthon.toml` (create one with `wyb init`).

```bash
pip install wybthon
wyb init my-app
cd my-app
wyb dev --open
```

## Behavior

- Builds the project with dev mode on, including any routes listed in `prerender`, so you develop against the same server-rendered pages you'll deploy. Production builds (`wyb build`) turn dev mode off; see [Deployment](deployment.md).
- Serves the build under the configured `base` path with client-route fallback to `200.html`. Requests outside the base path return 404.
- Watches the application directory (`app-dir`), `public/`, `index.html`, and `wybthon.toml`. A change, including a new or deleted file, triggers a rebuild and then a reload. Change detection polls modification times about every 0.5 seconds.
- Reports a failed build in the terminal and keeps serving the previous output, so a typo doesn't take the page down.
- Binds to the requested port or the next available one, up to 20 ports higher, and prints the project, the watched paths, and the URL it serves.
- Sends `Cache-Control: no-store` on every response, so the browser never reuses a stale build.

## Options

- `--dir`: the project directory (default `.`).
- `--host` (default `127.0.0.1`) and `--port` (default `8000`).
- `--open`: open the default browser to the app after the server starts.
- `--open-path`: open this path instead of the app's base path, for example `/about`.

To expose the server on your LAN or from a container, use `--host 0.0.0.0` and open the page via your machine's IP.

## How reloads work

Each page the dev build writes includes a small script that subscribes to `GET /__sse` and reloads on a `reload` event. After a successful rebuild, the server sends that event to every connected page. A full page reload means Pyodide boots again, so expect a short delay between saving a file and seeing the change.

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

- **"has no wybthon.toml."** The dev server only serves projects. Run it from the project directory, pass `--dir path/to/project`, or create a project with `wyb init`.
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
