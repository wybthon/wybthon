### Dev Server

Run a static server with auto-reload over SSE.

```bash
pip install .
wyb dev --dir . --host 127.0.0.1 --port 8000 --watch src examples --open \
  --mount /=. --mount /examples=examples --mount /src=src
```

Behavior:

- Watches `--watch` directories for file mtime changes
- Notifies browser via `/__sse` events; demo subscribes and reloads the page
- Binds to the requested port or the next available up to +20
- Serves additional static directories using `--mount /prefix=path` (repeatable)
- Optionally opens the browser with `--open` and `--open-path /examples/demo/`
- Prints the resolved host/port, selected port (if your requested one was busy), active mounts, and watched paths at startup

Options:

- `--mount /prefix=path`: mount filesystem `path` at the given URL prefix. The longest-prefix match wins.
- `--open`: open the default browser to the server URL after it starts.
- `--open-path`: append this path when opening the browser, e.g. `/examples/demo/`.

#### Advanced usage

- Multiple mounts and base URLs
  - The server maps URL prefixes to filesystem directories. The longest-prefix match wins.
  - Example: serve repo root at `/`, demo at `/examples`, and source at `/src`:

    ```bash
    wyb dev --dir . \
      --mount /=. \
      --mount /examples=examples \
      --mount /src=src \
      --open --open-path /examples/demo/
    ```

- Host/port selection and fallbacks
  - Defaults: `--host 127.0.0.1`, `--port 8000`.
  - If the requested port is busy, the server tries the next 20 ports and prints which one was selected.
  - To expose on your LAN or containers, use `--host 0.0.0.0` and open via your machine IP.

- Auto-open behavior
  - `--open` launches your default browser to the server URL.
  - If `--open-path` is omitted, the server heuristically opens `/` if `index.html` exists under `--dir`, otherwise `/examples/demo/` if present, otherwise `/`.

- Watching and reload delay
  - `--watch` accepts a list of directories; defaults to `src examples`.
  - File change detection is based on mtimes and checks ~every 0.5s. Expect a ~0.5–1.5s full page reload.
  - To disable auto-reload entirely, pass `--watch` with no values:

    ```bash
    wyb dev --dir . --watch --mount /=.
    ```

- SSE endpoint for reloads
  - The dev server exposes `GET /__sse` which streams `reload` events. The demo subscribes and calls `location.reload()`.
  - Integrate into your own app with a minimal client:

    ```js
    const es = new EventSource("/__sse");
    es.addEventListener("reload", () => location.reload());
    ```

- Cache busting in development
  - All responses include `Cache-Control: no-store, max-age=0`.
  - For ES modules, also append a timestamp query param to avoid module graph caching by the browser:

    ```html
    <script type="module">
      import(`./bootstrap.js?v=${Date.now()}`);
    </script>
    ```

- Path safety and traversal
  - The server sanitizes paths (`.`, `..`) before mapping to the filesystem; use mounts instead of relative escapes.
  - For a base-path style setup, mount your app under a prefix (e.g., `--mount /app=dist`) and open `--open-path /app/`.

- Not for production
  - This server is built on Python's `http.server` and is intended for development only.

#### Troubleshooting

- Auto-reload not firing
  - Confirm the dev server is running and `GET /__sse` shows an open EventSource connection in your browser's Network panel.
  - Ensure your changed files live under the `--watch` directories; add or adjust entries accordingly.
  - Behind proxies: make sure `/__sse` is passed through unbuffered (e.g., Nginx `proxy_buffering off;` and `X-Accel-Buffering: no`).

- Stale assets
  - Verify `Cache-Control: no-store` on responses. For modules, include a `?v=${Date.now()}` cache-buster as shown above.

- Port is already in use
  - The server will pick the next free port and print a notice. If you need the exact port, stop the conflicting process.
  - macOS example: `lsof -i :8000` then `kill -9 <PID>`.

- Browser did not open
  - `--open` relies on the system default browser; some headless or remote setups may block it.
  - Provide an explicit `--open-path` or copy the printed URL into your browser manually.

- Mounts not serving as expected
  - Prefixes must start with `/` (added automatically if omitted). Paths are resolved relative to `--dir` when not absolute.
  - When multiple mounts could match, the longest URL prefix wins. Check the startup "Mounts:" list to verify mapping.

- Exposing on the network
  - Use `--host 0.0.0.0` and ensure firewalls allow inbound traffic to the selected port.

See also: the general troubleshooting page under Meta → Troubleshooting.

Cache busting (development):

- The server sends `Cache-Control: no-store` for all static responses to avoid stale assets during development.
- The demo HTML dynamically imports `bootstrap.js` with a timestamp query param to ensure the module itself is refreshed:

```html
<script type="module">
  const v = Date.now();
  import(`./bootstrap.js?v=${v}`);
\/script>
```

Error overlay (development only):

- The demo `bootstrap.js` now shows a lightweight in-browser overlay when a Python exception or JS error occurs during app startup. It also listens for unhandled promise rejections.
- The overlay is dismissed via the "Dismiss" button and will be replaced on subsequent errors.
