### Dev Server

Run a static server with auto-reload over SSE.

```bash
pip install .
wyb dev --dir . --host 127.0.0.1 --port 8000 --watch src examples
```

Behavior:

- Watches `--watch` directories for file mtime changes
- Notifies browser via `/__sse` events; demo subscribes and reloads the page
- Binds to the requested port or the next available up to +20

> TODO: Document using a custom handler or mounting additional static paths.
