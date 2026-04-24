### wybthon.dev

::: wybthon.dev

#### What's in this module

`dev` implements the simple threaded development server invoked by the
`wyb dev` command. It serves static files from your project, mounts
extra directories at custom URL prefixes, and exposes a Server-Sent
Events (SSE) endpoint at `/__sse` for live reload.

You usually run it via the CLI:

```bash
wyb dev --dir . --port 8000 --watch src --watch examples
```

| Flag | Default | Description |
| --- | --- | --- |
| `--dir` | `.` | Root directory to serve. |
| `--host` | `127.0.0.1` | Host interface to bind. |
| `--port` | `8000` | Starting port (auto-increments on conflict). |
| `--watch` | `src`, `examples` | Directories to watch for live reload. |
| `--mount` | *(none)* | `path=/url/prefix` mount; can be repeated. |

#### How live reload works

1. The browser opens an `EventSource` to `/__sse`.
2. The server walks `--watch` directories and notes file modification
   times.
3. When something changes, the server pushes a `reload` event over SSE.
4. The page reloads itself in response.

The demo's `index.html` includes a tiny snippet that listens for these
events; you can copy it into your own apps.

#### See also

- [Getting started](../getting-started.md): running the demo.
- [Dev server guide](../guides/dev-server.md): deeper walkthrough.
- [Deployment guide](../guides/deployment.md): production hosting.
