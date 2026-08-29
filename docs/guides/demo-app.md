### Demo Apps

Wybthon's demo applications live in standalone repositories under the [wybthon GitHub organization](https://github.com/wybthon). Each is a complete static site: Python in the browser via Pyodide, no JavaScript build step, and each installs Wybthon from PyPI the same way your own app would.

| Repository | What it shows |
| --- | --- |
| [demo-template](https://github.com/wybthon/demo-template) | A minimal starter: `index.html`, a Pyodide `bootstrap.js`, and an `app/` package ready to edit. Fork or clone it to begin a new app. |
| [reactive-profiler](https://github.com/wybthon/reactive-profiler) | An interactive visualization of run-once components and fine-grained reactive holes, including a live profiler that tallies signal writes and DOM mutations. Live at [profiler.wybthon.com](https://profiler.wybthon.com/). |
| [data-lab](https://github.com/wybthon/data-lab) | Explore, analyze, visualize, and export data entirely in the browser. A larger app exercising forms, stores, flow control, and async data. |
| [photo-lab](https://github.com/wybthon/photo-lab) | Resize, compress, convert, and strip image metadata privately in the browser. Demonstrates file handling and JS interop. |

#### Running a demo locally

Every demo is a static site, so the workflow is the same:

```bash
git clone https://github.com/wybthon/demo-template.git
cd demo-template
pip install wybthon
wyb dev --dir . --watch app --open
```

The `wyb dev` server provides hot reload over SSE; see the [dev server guide](dev-server.md).

#### How the demos bootstrap

Each demo follows the same pattern:

- `index.html` loads `bootstrap.js` as an ES module.
- `bootstrap.js` loads Pyodide, installs Wybthon (from PyPI via `micropip`, or by copying source files into the Pyodide filesystem), copies the app package under `/app`, then calls `app.main.main()`.
- Folders under `app/` mirror routes and components.

The [Pyodide guide](pyodide.md) covers the runtime details, including module loading and lazy imports.

## Next steps

- Start from the [demo-template](https://github.com/wybthon/demo-template) for your own app.
- Explore the [Examples](../examples.md) for individual feature walkthroughs.
- See the [Dev server guide](dev-server.md) for the local feedback loop.
