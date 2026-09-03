### wybthon.dev

::: wybthon.dev

#### What's in this module

`dev` is the threaded development server behind the `wyb dev` command.
It serves static files from your project, mounts extra directories at
custom URL prefixes, exposes a `/__manifest` endpoint that lists `.py`
files so bootstrap scripts can discover modules, and pushes a `reload`
event over Server-Sent Events at `/__sse` when watched files change.

| Name | Description |
| --- | --- |
| [`main`][wybthon.dev.main] | CLI entry point (`wyb dev ...`). |
| [`serve`][wybthon.dev.serve] | Start the server programmatically with the same options. |
| [`SSEHandler`][wybthon.dev.SSEHandler] | The request handler: static files, `/__sse`, `/__manifest`, and no-cache headers. |

```bash
wyb dev --dir . --port 8000 --watch src app --open --open-path /app/
```

| Flag | Default | Description |
| --- | --- | --- |
| `--dir` | repository root | Root directory to serve. |
| `--host` | `127.0.0.1` | Host interface to bind. |
| `--port` | `8000` | Starting port (auto-increments on conflict). |
| `--watch` | `src` | Directories to watch for live reload. |
| `--mount` | none | `path=/url/prefix` mount; repeatable. |
| `--open` | off | Open a browser to the server URL. |
| `--open-path` | none | Path to open, such as `/app/`. |

Live reload: the page opens an `EventSource` to `/__sse`; the server
polls the `--watch` directories for modification-time changes and
broadcasts `reload`; the page reloads itself. A small `EventSource`
snippet in `index.html` is all that's needed; see the
[dev server guide](../guides/dev-server.md).

#### See also

- [Getting started](../getting-started.md)
- [Guides: Dev server](../guides/dev-server.md)
- [Guides: Deployment](../guides/deployment.md)
