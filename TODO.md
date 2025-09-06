## Wybthon Roadmap (Client-Side Python SPA Framework)

A prioritized, numbered list of the top implementation tasks to evolve Wybthon into a practical CSR/SPA framework using client-side Python (Pyodide). The list balances MVP features with a path to release on PyPI.

1. Upgrade Pyodide bootstrap and loader
   - Use latest Pyodide CDN and `loadPyodide` API; remove `setTimeout` workaround.
   - Add integrity/crossorigin as appropriate; centralize bootstrap in a small JS shim.
   - Ensure `runPythonAsync` wiring calls a single Python `bootstrap()`/`main()` entry.

2. Define proper package structure for PyPI
   - Move library to `src/wybthon/` (PEP 517/518) with `__init__.py` and modules.
   - Add `pyproject.toml` (name, version, license, classifiers, deps, readme, urls).
   - Keep browser assets (templates/examples) under `examples/` and `site/`.

3. Expand DOM abstraction
   - Extend `Element` to support `set_attr`, `set_style`, `class_list`, `on(event, ...)`, and cleanup.
   - Provide safe HTML insertion and text utilities.
   - Add `query(selector, within=None)` helpers and `ref` handles.

4. Introduce a Virtual DOM (VNode) representation
   - `VNode(tag, props, children, key)` dataclass + factory `h(tag, props, *children)`.
   - Render root: `render(vnode, container)` and patcher: keyed diff for children.
   - Map props to DOM attributes, styles, dataset, and event listeners.

5. Component model (class and function components)
   - Class components: `render(self) -> VNode`, lifecycle hooks.
   - Function components: `def Component(props): return VNode` with hooks-like API.
   - Support `children` and `key` props; predictable update semantics.

6. Reactive state primitives and scheduler
   - `Signal[T]`, `computed`, `effect`, and `batch` updates.
   - Dependency tracking and microtask-based scheduler to coalesce renders.
   - Trigger component re-render on signal change; avoid unnecessary subtree updates.

7. Lifecycle and cleanup
   - `on_mount`, `on_update`, `on_unmount`, `on_cleanup` per component instance.
   - Ensure event listeners, timers, and effects are disposed on unmount.

8. Event system with delegation
   - Event delegation at the root; map `on_click`, `on_input`, etc., to Python callbacks.
   - Provide `prevent_default`, `stop_propagation`; pass normalized event objects.

9. Context API (dependency injection)
   - `create_context(default)`, `Provider(value)`, `use_context(ctx)` to avoid prop drilling.

10. Router (History API)
   - Client-side router with `Route` definitions, dynamic segments, query/params.
   - `Link` component, `navigate(path)`, guards, and nested routes.

11. Async data utilities
   - `use_resource(fetcher)` with loading/error states and cancellation.
   - Example: fetch JSON and render with suspense-like fallback.

12. Forms and two-way binding
   - Controlled inputs via signals; helpers for common input types.
   - Validation hooks; form submission helpers.

13. Error boundaries
   - Catch exceptions in render/effects; show fallback UI without tearing down app.

14. Dev server workflow and HMR-lite
   - Simple file-watcher to auto-reload the page on Python/HTML changes.
   - Keep `start_web_server.sh` for zero-dep dev; optionally add a Python CLI `wyb dev`.

15. Testing and CI (browser + Pyodide)
   - Unit tests for VDOM diff, signals, scheduler (pytest).
   - Browser integration tests (Playwright) executing Pyodide bundles.
   - GitHub Actions to run tests on push/PR.

16. Documentation site and examples
   - MkDocs or Sphinx with tutorials and API reference.
   - Examples: Counter, Todos, Router navigation, Async data fetch, Forms.

17. Performance pass
   - Keyed list updates, large list benchmarks, event delegation overhead.
   - Avoid frequent `innerHTML`; prefer node-level patching; measure with timeline.

18. Packaging for PyPI
   - Build `sdist` and `wheel`; verify install with `pip` and use in Pyodide via `micropip`.
   - Add versioning (SemVer), changelog, LICENSE, and `README` long_description.
   - Publish using trusted publisher; document usage in README and docs.

19. Developer tooling and linting
   - Ruff + Black + Mypy configuration; pre-commit hooks.
   - Type annotations across public APIs; clear exceptions and error messages.

20. Optional advanced features (post-MVP)
   - Portals, fragments, refs forwarding; suspense-like streaming; server-hydration.
   - Devtools panel (DOM tree + signals inspector) and plugin API.

---

Notes on current repo state (from scan):
- `libs/wybthon/index.html` bootstraps Pyodide v0.18.0 with a `setTimeout` call.
- `libs/wybthon/wybthon.py` defines `Element`, `BaseComponent`, and example components using async `render`.
- `libs/wybthon/start_web_server.sh` runs a simple `python -m http.server`.
- Recommend migrating to `src/wybthon/` layout and adding `pyproject.toml` ahead of PyPI.
