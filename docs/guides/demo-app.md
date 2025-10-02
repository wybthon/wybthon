### Demo App

The demo is served from `examples/demo/`.

- `index.html` loads `bootstrap.js`
- `bootstrap.js` loads Pyodide, mounts the library from `src/wybthon/`, and copies demo files under `/app` inside Pyodide FS, then calls `app.main.main()`

Folders under `examples/demo/app/` mirror routes and components.

> TODO: Describe each demo page and how routing is wired in `app/routes.py`.
