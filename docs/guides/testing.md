### Testing

Approaches:

- Unit test pure modules (e.g., `reactivity`) in CPython
- For browser-dependent code, use Pyodide in a headless browser via the end-to-end suite

#### Browser E2E suite (Playwright + Pyodide)

The `e2e` job in CI runs the full browser suite under `tests/e2e/`. It has two
parts, both marked with the `e2e` pytest marker and both exercising the real
Pyodide runtime in headless Chromium:

1. **Feature fixture app** (`tests/e2e/app/`): a dedicated single-page app with
   **one route per framework feature** (reactivity, reactive holes, props,
   events, context, flow control, forms, stores, suspense, error boundary,
   components/lifecycle, portal, lazy loading, and the router). Each
   per-feature test module (`tests/e2e/test_*.py`) drives that route and asserts
   behaviour through stable `data-testid` selectors.
2. **Demo smoke test** (`tests/e2e/test_pyodide_smoke.py`): loads
   `examples/demo/index.html` and verifies the demo boots and renders.

Design choices that keep the suite fast and deterministic:

- **Boot Pyodide once.** The fixture app is booted a single time per session
  (`fixture_page` in `tests/e2e/conftest.py`); individual tests navigate between
  features using the History-API router instead of reloading the page, so the
  multi-second Pyodide cold start is paid only once.
- **Isolation between tests.** The `goto_feature` helper bounces through a
  `/blank` route before navigating to the target feature, forcing the previous
  feature's component tree to unmount so each test starts from a clean mount.
- **Stable selectors.** Components expose `data-testid` attributes (see the
  `tid` helper in `tests/e2e/app/testkit.py`) rather than relying on text or DOM
  structure.
- **Fail fast on boot errors.** `bootstrap.js` records any boot failure on
  `window.__WYB_E2E_ERROR`; the readiness wait surfaces it as a test error
  instead of timing out.

Run locally:

```bash
pip install -e ".[dev]"
python -m playwright install chromium

# full browser suite (fixture app + demo smoke test)
pytest -q -m e2e tests/e2e

# a single feature module
pytest -q -m e2e tests/e2e/test_error_boundary.py
```

Notes:

- The suite serves the repo root via `wyb dev` so `bootstrap.js` can fetch
  `src/wybthon` and `tests/e2e/app` and use the `/__manifest` endpoint to
  discover Python files.
- Tests use generous timeouts (Pyodide initialization can take time in CI), and
  the default pytest config (`addopts = -m "not e2e"`) excludes the browser
  suite from the fast unit run; pass `-m e2e` to opt in.
- The fixture app under `tests/e2e/app/` is Pyodide-runtime code (it uses
  absolute `app.*` imports that only resolve inside the Pyodide filesystem), so
  it's excluded from mypy and is never imported by the CPython unit tests.

#### Unit tests

For Python-only logic (e.g., `reactivity`, `forms` helpers), write regular `pytest` tests under `tests/`.

Several core modules are browser-agnostic and can be tested without any
stubs:

- `wybthon.vnode`: VNode creation, `h()`, `Fragment`, `memo()`
- `wybthon.error_boundary`: ErrorBoundary component logic
- `wybthon.suspense`: Suspense component logic
- `wybthon._warnings`: dev-mode error reporting

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

## Next steps

- Read the [Contributing guide](../meta/contributing.md) for the full local workflow.
- Browse the [Performance guide](performance.md) for benchmarking tips.
- See [Pyodide guide](pyodide.md) for browser environment notes.
