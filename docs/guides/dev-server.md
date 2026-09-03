# Dev server

`wyb dev` runs a static file server with auto-reload over Server-Sent Events (SSE).

```bash
pip install wybthon
wyb dev --dir . --host 127.0.0.1 --port 8000 --watch src app --open \
  --mount /=. --mount /src=src
```

## Behavior

- Watches the `--watch` directories for file modification-time changes.
- Notifies the browser through `/__sse`; subscribed pages reload themselves.
- Binds to the requested port or the next available one, up to 20 ports higher.
- Serves additional static directories with `--mount /prefix=path` (repeatable).
- Optionally opens the browser with `--open` and `--open-path /app/`.
- Exposes `/__manifest?dir=<path>`, which returns a JSON array of the `.py` files under a directory so a bootstrap script can copy a package into the Pyodide filesystem without a hardcoded file list.
- Prints the resolved host and port, the selected port if your requested one was busy, active mounts, and watched paths at startup.

## Options

- `--dir`: root directory to serve. The default points at the Wybthon checkout, so pass `--dir .` for your own project.
- `--host` (default `127.0.0.1`) and `--port` (default `8000`).
- `--watch`: directories to watch (default `src`). Pass `--watch` with no values to disable auto-reload.
- `--mount /prefix=path`: mount filesystem `path` at the given URL prefix. The longest matching prefix wins. Paths resolve relative to `--dir` unless absolute.
- `--open`: open the default browser to the server URL after it starts.
- `--open-path`: append this path when opening the browser, for example `/app/`.

## Advanced usage

### Multiple mounts and base URLs

The server maps URL prefixes to filesystem directories, longest prefix first. To serve the project root at `/`, your app at `/app`, and source at `/src`:

```bash
wyb dev --dir . \
  --mount /=. \
  --mount /app=app \
  --mount /src=src \
  --open --open-path /app/
```

For a base-path style setup, mount the built app under a prefix (`--mount /app=dist`), open `--open-path /app/`, and pass the same prefix to [`Router`][wybthon.Router] as `base_path="/app"`.

### Host and port selection

- Defaults: `--host 127.0.0.1`, `--port 8000`.
- If the requested port is busy, the server tries the next 20 ports and prints the one it picked.
- To expose the server on your LAN or from a container, use `--host 0.0.0.0` and open the page via your machine's IP.

### Watching and reload delay

- `--watch` accepts a list of directories; the default is `src`.
- Change detection polls modification times about every 0.5 seconds. Expect a 0.5 to 1.5 second full page reload.
- To disable auto-reload entirely:

    ```bash
    wyb dev --dir . --watch --mount /=.
    ```

### SSE endpoint for reloads

The server exposes `GET /__sse`, which streams `reload` events. Wire it into your own page with a minimal client:

```js
const es = new EventSource("/__sse");
es.addEventListener("reload", () => location.reload());
```

### Loading a package from the manifest

The E2E fixture in the Wybthon repository uses `/__manifest` to copy a whole Python package into Pyodide's filesystem:

```js
async function loadPyPackage(pyodide, manifestDir, fetchBase, mountRoot) {
  const files = await (await fetch(`/__manifest?dir=${encodeURIComponent(manifestDir)}`)).json();
  for (const f of files) {
    const dir = `${mountRoot}/${f}`.split("/").slice(0, -1).join("/");
    try { pyodide.FS.mkdirTree(dir); } catch {}
    const txt = await (await fetch(`${fetchBase}/${f}`)).text();
    pyodide.FS.writeFile(`${mountRoot}/${f}`, new TextEncoder().encode(txt));
  }
}

await loadPyPackage(pyodide, "app", "./app", "/app");
await pyodide.runPythonAsync("import sys; sys.path.insert(0, '/')");
```

Most apps install Wybthon itself with `micropip.install("wybthon")` and only copy their own `app/` package this way.

### Cache busting in development

- Every response carries `Cache-Control: no-store, max-age=0`.
- For ES modules, also append a timestamp query parameter so the browser doesn't reuse its module graph:

    ```html
    <script type="module">
      import(`./bootstrap.js?v=${Date.now()}`);
    </script>
    ```

### Path safety

The server sanitizes `.` and `..` segments before mapping a URL to the filesystem. Use mounts rather than relative escapes to reach directories outside `--dir`.

### Not for production

The dev server is built on Python's `http.server` and is intended for development only. See the [Deployment guide](deployment.md) for hosting.

## Troubleshooting

- **Auto-reload isn't firing.** Confirm the server is running and that `GET /__sse` shows an open EventSource connection in the browser's Network panel. Make sure the files you edit live under a `--watch` directory. Behind a proxy, pass `/__sse` through unbuffered (Nginx: `proxy_buffering off;` and `X-Accel-Buffering: no`).
- **Stale assets.** Verify `Cache-Control: no-store` on responses and add the `?v=${Date.now()}` cache-buster to module imports.
- **Port is already in use.** The server picks the next free port and prints a notice. If you need the exact port, stop the conflicting process (macOS: `lsof -i :8000`, then `kill <PID>`).
- **The browser didn't open.** `--open` relies on the system default browser; some headless or remote setups block it. Copy the printed URL instead.
- **Mounts aren't serving as expected.** Prefixes must start with `/` (added automatically if omitted). Check the startup "Mounts:" list to verify the mapping; the longest prefix wins.
- **Exposing on the network.** Use `--host 0.0.0.0` and allow inbound traffic to the selected port through your firewall.

See also the general troubleshooting page under Meta.

## Next steps

- See the [`dev`][wybthon.dev] API reference for the underlying server.
- Read the [Deployment guide](deployment.md) for production hosting.
- Browse [Examples](../examples.md) to see real apps running under the dev server.
