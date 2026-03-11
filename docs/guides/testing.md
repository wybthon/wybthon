### Testing

Approaches:

- Unit test pure modules (e.g., `reactivity`) in CPython
- For browser-dependent code, use Pyodide in a headless browser or test via demo pages

#### Pyodide smoke test (Playwright)

We include a minimal Playwright-based smoke test that loads the demo app in a headless Chromium instance with Pyodide, then asserts that key UI elements render.

- Location: `tests/e2e/test_pyodide_smoke.py`
- What it does: starts a simple HTTP server at the repo root, navigates to `examples/demo/index.html`, and waits for the demo title and `Hello, Python!` component to appear.

Run locally:

```bash
pip install -e ".[dev]"
python -m playwright install chromium
pytest -q -m e2e tests/e2e/test_pyodide_smoke.py
```

Notes:

- The demo bootstrap fetches directly from `src/wybthon` and `examples/demo/app` so serving the repo root is required.
- The test uses generous timeouts (up to 120s) since Pyodide initialization can take time in CI.

#### Unit tests

For Python-only logic (e.g., `reactivity`, `forms` helpers), write regular `pytest` tests under `tests/`.

Several core modules are browser-agnostic and can be tested without any
stubs:

- `wybthon.vnode` — VNode creation, `h()`, `Fragment`, `memo()`
- `wybthon.error_boundary` — ErrorBoundary component logic
- `wybthon.suspense` — Suspense component logic
- `wybthon._warnings` — dev-mode error reporting

For browser-dependent modules (`reconciler`, `props`, `dom`, `events`), the
existing test files use `_install_stubs()` to inject fake `js` and `pyodide`
modules before reloading the Wybthon modules under test.

#### Coverage

We use `pytest-cov` for coverage and enforce a minimum in CI.

- Install locally:

```bash
pip install -e ".[dev]"
```

- Run tests with coverage:

```bash
pytest -q --cov=wybthon --cov-branch --cov-report=term-missing
```

In CI, coverage is generated as XML and the build fails if coverage drops below the configured threshold.
