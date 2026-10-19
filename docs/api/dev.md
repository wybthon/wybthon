### wybthon.dev

::: wybthon.dev

#### What's in this module

`dev` is the `wyb` command. It works on projects: a directory with a
`wybthon.toml`, created by `wyb init`. `wyb dev` builds the project in
development mode, serves the build, rebuilds when a source file changes,
and pushes a `reload` event over Server-Sent Events at `/__sse` so open
pages refresh. `wyb build` writes a production build, which turns dev
mode off, and `wyb preview` serves one. Every built page carries its
build manifest inline (`<script type="application/json"
id="wyb-manifest">`) and preloads what boot needs: a
`<link rel="modulepreload">` for Pyodide's `pyodide.mjs`, and
`<link rel="preload" as="fetch" crossorigin>` for the runtime and
application archives, so they download in parallel with Pyodide.

| Name | Description |
| --- | --- |
| [`main`][wybthon.dev.main] | CLI entry point (`wyb init`, `wyb dev`, `wyb build`, `wyb preview`). |
| [`serve`][wybthon.dev.serve] | `serve(directory=".", host="127.0.0.1", port=8000, open_browser=False, open_path=None)`: the `wyb dev` server, callable from Python. |

```bash
wyb init my-app
wyb dev --dir my-app --port 8000 --open
wyb build --dir my-app --base /app/
wyb preview --dir my-app/dist
```

| Command | Flag | Default | Description |
| --- | --- | --- | --- |
| `wyb dev` | `--dir` | `.` | Project directory (containing `wybthon.toml`). |
| `wyb dev` | `--host` | `127.0.0.1` | Host interface to bind. |
| `wyb dev` | `--port` | `8000` | Starting port (tries the next 20 on conflict). |
| `wyb dev` | `--open` | off | Open a browser at the app's base path. |
| `wyb dev` | `--open-path` | none | Path to open instead of the base path. |
| `wyb build` | `--dir` | `.` | Project directory. |
| `wyb build` | `--out` | `<dir>/dist` | Output directory. |
| `wyb build` | `--base` | from `wybthon.toml` | Base URL path the app is served from. |
| `wyb preview` | `--dir`, `--host`, `--port` | `dist`, `127.0.0.1`, `8000` | Serve a production build. |

Live reload: `wyb dev` watches the app directory, `public/`,
`index.html`, and `wybthon.toml`, rebuilds on any change, and
broadcasts `reload`; the snippet it injects into each served page
reloads it. The static-directory mode of earlier versions, with its
`/__manifest` endpoint and `--mount` and `--watch` flags, is gone; every
served directory is a project. See the
[dev server guide](../guides/dev-server.md).

#### See also

- [Getting started](../getting-started.md)
- [Guides: Dev server](../guides/dev-server.md)
- [Guides: Deployment](../guides/deployment.md)
