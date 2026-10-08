# Demo apps

Wybthon's demo applications live in standalone repositories under the [wybthon GitHub organization](https://github.com/wybthon). Each is a complete static site: Python in the browser via Pyodide, no JavaScript build step, and each installs Wybthon from PyPI the same way your own app would.

| Repository | What it shows |
| --- | --- |
| [demo-template](https://github.com/wybthon/demo-template) | A minimal starter: `index.html`, a Pyodide `bootstrap.js`, and an `app/` package ready to edit. Fork or clone it to begin a new app. |
| [reactive-profiler](https://github.com/wybthon/reactive-profiler) | An interactive visualization of run-once components and fine-grained reactive holes, including a live profiler that tallies signal writes and DOM mutations. Live at [profiler.wybthon.com](https://profiler.wybthon.com/). |
| [data-lab](https://github.com/wybthon/data-lab) | Explore, analyze, visualize, and export data entirely in the browser. A larger app exercising forms, stores, flow control, and async data. |
| [photo-lab](https://github.com/wybthon/photo-lab) | Resize, compress, convert, and strip image metadata privately in the browser. Demonstrates file handling and JS interop. |

!!! note "Versions"
    The demos are separate repositories with their own release cadence, so they may target an earlier Wybthon API than the one these docs describe. Use `wyb init` for a starter that matches the installed version's API.

## Running a demo locally

A demo that contains a `wybthon.toml` is a Wybthon project, so the workflow is the same as for your own app:

```bash
git clone https://github.com/wybthon/demo-template.git
cd demo-template
pip install wybthon
wyb dev --open
```

`wyb dev` builds the project, serves it, and reloads the page when a source file changes; see the [dev server guide](dev-server.md). A demo that ships its own `index.html` and `bootstrap.js` without a `wybthon.toml` is a plain static site, so serve it with any static file server (`python -m http.server`) and follow its README.

## How a project boots

Wybthon projects follow the same pattern:

- `wybthon.toml` names the entry function (`entry = "app.main:app"`), the mount selector, and the routes to prerender.
- `wyb build` packages Wybthon and the `app/` package into archives and writes a bootstrap that loads Pyodide and the archives concurrently, then imports the entry.
- `app/main.py` returns the root view from its entry function, typically wrapping the tree in [`Errored`][wybthon.Errored] and [`Loading`][wybthon.Loading] boundaries around a [`Router`][wybthon.router.Router] from `wybthon.router`. The bootstrap renders it, or hydrates the prerendered HTML.
- Folders under `app/` mirror routes and components, and route pages are often loaded with [`lazy`][wybthon.lazy] so the initial import stays small.

The [Pyodide guide](pyodide.md) covers the runtime details, and the [Deployment guide](deployment.md) covers the build.

## Next steps

- Start from the [demo-template](https://github.com/wybthon/demo-template) for your own app.
- Explore the [Examples](../examples.md) for individual feature walkthroughs.
- See the [Dev server guide](dev-server.md) for the local feedback loop.
