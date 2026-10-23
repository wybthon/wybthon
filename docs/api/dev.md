### wybthon.dev

::: wybthon.dev

#### What's in this module

`dev` is the `wyb` command. It works on projects: a directory with a
`wybthon.toml`, created by `wyb init`. `wyb dev` builds the project in
development mode, serves the build, rebuilds when a source file changes,
and pushes a `reload` event over Server-Sent Events at `/__sse` so open
pages refresh. `wyb build` writes a production build, which turns dev
mode off, and `wyb preview` serves one. Both `wyb dev` and `wyb build`
run every application module through the [compiler](compiler.md), so a
malformed template fails the build with its file and line, and they
ship the compiled bytecode (when the build's Python matches the Pyodide
runtime's; see [Deployment](../guides/deployment.md)), so the page never
parses a template at run time. `wyb run` runs a single script with
its templates compiled. Every built page carries its
build manifest inline (`<script type="application/json"
id="wyb-manifest">`) and preloads what boot needs: a
`<link rel="modulepreload">` for Pyodide's `pyodide.mjs`, and
`<link rel="preload" as="fetch" crossorigin>` for the runtime and
application archives, so they download in parallel with Pyodide.

| Name | Description |
| --- | --- |
| [`main`][wybthon.dev.main] | CLI entry point (`wyb init`, `wyb dev`, `wyb build`, `wyb preview`, `wyb run`). |
| [`serve`][wybthon.dev.serve] | `serve(directory=".", host="127.0.0.1", port=8000, open_browser=False, open_path=None)`: the `wyb dev` server, callable from Python. |
| [`run_script`][wybthon.dev.run_script] | `run_script(path, argv)`: what `wyb run` does, callable from Python. |

```bash
wyb init my-app
wyb dev --dir my-app --port 8000 --open
wyb build --dir my-app --base /app/
wyb preview --dir my-app/dist
wyb run scripts/seed.py --verbose
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
| `wyb run` | `script [args ...]` | none | Run a Python script as `__main__` with its templates compiled; the arguments after it are passed to the script. |

Live reload: `wyb dev` watches the app directory, `public/`,
`index.html`, and `wybthon.toml`, rebuilds on any change, and
broadcasts `reload`; the snippet it injects into each served page
reloads it. The static-directory mode of earlier versions, with its
`/__manifest` endpoint and `--mount` and `--watch` flags, is gone; every
served directory is a project. See the
[dev server guide](../guides/dev-server.md).

`wyb run script.py` is for code outside a project: a script that
renders components with [`wybthon.testing`](testing.md) or
[`wybthon.server`](server.md), a benchmark, or a quick experiment.
`python script.py` compiles the `__main__` module before Wybthon is
imported, so its templates aren't compiled, and dev mode raises
[`TemplateError`][wybthon.TemplateError] when a dynamic expression in
one of them was evaluated once. `wyb run` compiles the script itself,
installs the import hook for the modules it imports, puts the script's
directory first on `sys.path`, and sets `sys.argv`, so the script
behaves as it would inside an application.

```bash
wyb run render_page.py --out page.html  # sys.argv[1:] == ["--out", "page.html"]
```

#### See also

- [Getting started](../getting-started.md)
- [Guides: Dev server](../guides/dev-server.md)
- [Guides: Deployment](../guides/deployment.md)
- [Compiler](compiler.md)
