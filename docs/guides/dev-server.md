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
