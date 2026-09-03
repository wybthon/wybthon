# Testing

Wybthon's reactive core, VDOM, and reconciler are pure Python, so almost everything can be tested in CPython with `pytest`. A stub backend applies the same DOM ops the JavaScript kernel would, against in-memory nodes. Browser-specific behavior (real layout, real events, Pyodide itself) is covered by a Playwright suite.

Two rules cover most of what's different about testing reactive code:

1. **Writes are staged.** After `set_count(1)`, `count()` still returns the old value until the graph flushes. In the browser that happens on a microtask; in a test, call [`flush`][wybthon.flush].
2. **Effects run after commit.** `create_effect`'s first run is deferred to the next flush, so assert after a `flush()`.

## Unit tests in CPython

### The reactive core, no DOM

Signals, memos, effects, and stores need no fixtures at all:

```python
from wybthon import create_effect, create_memo, create_signal, flush


def test_memo_and_effect():
    count, set_count = create_signal(0)
    doubled = create_memo(lambda: count() * 2)
    seen: list[int] = []

    create_effect(doubled, lambda value, prev: seen.append(value))
    flush()                    # first effect run
    assert seen == [0]

    set_count(1)
    set_count(lambda n: n + 1)  # functional updates compose
    assert count() == 0         # still staged
    flush()
    assert count() == 2
    assert seen == [0, 4]       # one effect run per flush
```

### Rendering with the stub backend

The repository's `tests/conftest.py` provides two fixtures:

- `wyb`: installs fake `js` and `pyodide` modules, reloads the browser-dependent Wybthon modules, and installs a `kernel.PythonBackend` over an in-memory `StubDocument`. It yields a dict of the reloaded modules keyed by name (`kernel`, `dom`, `events`, `reconciler`, `reactivity`, `flow`, `store`, and so on).
- `root_element`: a fresh `Element` wrapping a stub `<div>`; `root_element.element` is the raw stub node.

Because `kernel`, `dom`, `events`, and `reconciler` are reloaded per test, take `render` from the fixture (`wyb["reconciler"].render`) rather than from a module-level import. Importing the reactive primitives and HTML helpers at module top is fine; they aren't reloaded.

```python
from conftest import collect_texts

from wybthon import Prop, button, component, create_signal, div, flush, p


def texts(node):
    return [t for t in collect_texts(node) if t]


@component
def Counter(label: Prop[str]):
    count, set_count = create_signal(0)
    return div(
        p(label, ": ", count),
        button("+", on_click=lambda e: set_count(lambda n: n + 1)),
    )


def test_counter_renders_and_updates(wyb, root_element):
    root = wyb["reconciler"].render(Counter(label="Clicks"), root_element)
    assert texts(root_element.element) == ["Clicks", ": ", "0"]

    container = [n for n in root_element.element.childNodes if n.tag == "div"][0]
    button_node = [n for n in container.childNodes if n.tag == "button"][0]
    wyb["kernel"]._backend.dispatch("click", button_node)   # runs handlers, then flushes
    assert texts(root_element.element) == ["Clicks", ": ", "1"]

    root.dispose()
    assert root_element.element.childNodes == []
```

Notes on the stub DOM:

- `collect_texts(node)` returns every text-node value in a subtree, including empty text nodes; filter them as above. `texts_of_children(node)` returns the text of each direct child.
- Stub nodes expose `.tag`, `.nodeValue`, `.childNodes`, `.parentNode`, `.attributes` (a dict of strings), `.classList.contains(...)`, `.style._props`, `.value`, and `.checked`. Fragments and holes insert comment markers, so filter on `.tag` when counting element children.
- `wyb["kernel"]._backend.dispatch(event_type, node)` simulates a bubbling native event through the delegation root and flushes afterward, exactly like the JS kernel's listener. Pass `payload={"value": "x"}` to simulate input values.

### Testing props and holes

```python
from conftest import collect_texts

from wybthon import Prop, component, create_signal, flush, p


def test_prop_updates_without_rerunning_body(wyb, root_element):
    name, set_name = create_signal("Ada")
    runs: list[int] = []

    @component
    def Greeting(name: Prop[str]):
        runs.append(1)
        return p("Hello, ", name)

    wyb["reconciler"].render(Greeting(name=name), root_element)
    set_name("Grace")
    flush()
    assert [t for t in collect_texts(root_element.element) if t] == ["Hello, ", "Grace"]
    assert runs == [1]
```

### Async tests

Async memos, actions, and `Loading` boundaries need an event loop. Wrap the test body in an `async def` and run it with `asyncio.run`. Alternate `flush()` with `await asyncio.sleep(0)` so coroutines get a turn and their results are committed:

```python
import asyncio

from conftest import collect_texts

from wybthon import Loading, component, create_memo, div, flush, p


async def tick(n: int = 3) -> None:
    for _ in range(n):
        flush()
        await asyncio.sleep(0)
    flush()


def test_loading_shows_fallback_then_content(wyb, root_element):
    async def main() -> None:
        gate = asyncio.Event()

        @component
        def UserCard():
            async def load():
                await gate.wait()
                return {"name": "Ada"}

            user = create_memo(load)
            return p("User: ", lambda: user()["name"])

        wyb["reconciler"].render(div(Loading(lambda: UserCard(), fallback=p("Loading..."))), root_element)
        await tick()
        assert [t for t in collect_texts(root_element.element) if t] == ["Loading..."]

        gate.set()
        await tick()
        assert [t for t in collect_texts(root_element.element) if t] == ["User: ", "Ada"]

    asyncio.run(main())
```

Outside a component, create primitives under [`create_root`][wybthon.create_root] so they have an owner: `user = create_root(lambda dispose: create_memo(load))`. [`resolve`][wybthon.resolve] awaits an async memo's next settled value, which keeps tests short: `assert await resolve(user) == "data"`.

### Stores, router, and forms

- Store writes are staged like signal writes. Python doesn't allow assignment inside a lambda, so write draft functions with `def`, pass them to `set_store`, and `flush()` before asserting on reads.
- Outside a browser, [`navigate`][wybthon.navigate] only updates the `current_path` signal. Call `flush()` afterward.
- Form bindings return handler functions; call them with a fake event object exposing `.target.value` (or use `dispatch` with a payload) and `flush()`.

### Dev-mode diagnostics

Dev-mode warnings print to `stderr`; capture them with pytest's `capsys`. Warnings are deduplicated per process, so call `wybthon._warnings._reset_warning_dedupe()` at the start of a test that asserts on one. A write inside a memo raises `WriteInScopeError` when the memo is read (`pytest.raises(WriteInScopeError)` around `bad()`); a write inside a single-form effect surfaces through the effect's `error=` handler on the next `flush()`.

## Browser E2E suite (Playwright and Pyodide)

The `e2e` job in CI runs the browser suite under `tests/e2e/`. All tests carry the `e2e` pytest marker and exercise the real Pyodide runtime (314.0.6) in headless Chromium against a **feature fixture app** (`tests/e2e/app/`): a single-page app with one route per framework feature (reactivity, holes, props, events, context, flow control, forms, stores, loading, error boundaries, lifecycle, portal, lazy loading, router). Each per-feature test module (`tests/e2e/test_*.py`) drives that route and asserts through stable `data-testid` selectors.

Design choices that keep the suite fast and deterministic:

- **Boot Pyodide once.** The fixture app boots a single time per session (`fixture_page` in `tests/e2e/conftest.py`); tests navigate between features with the History-API router instead of reloading the page.
- **Isolation between tests.** The `goto_feature` helper bounces through a `/blank` route first, forcing the previous feature's tree to unmount.
- **Stable selectors.** Components expose `data-testid` attributes (see the `tid` helper in `tests/e2e/app/testkit.py`).
- **Fail fast on boot errors.** `bootstrap.js` records any boot failure on `window.__WYB_E2E_ERROR`, and the readiness wait surfaces it as a test error instead of a timeout.

Run locally:

```bash
uv sync --group dev
uv run python -m playwright install chromium

# full browser suite
uv run pytest -q -m e2e tests/e2e

# a single feature module
uv run pytest -q -m e2e tests/e2e/test_error_boundary.py
```

Notes:

- The suite serves the repository root through `wyb dev` so `bootstrap.js` can fetch `src/wybthon` and `tests/e2e/app` and use the `/__manifest` endpoint to discover Python files.
- The default pytest configuration (`addopts = -m "not e2e"`) excludes the browser suite from the fast unit run; pass `-m e2e` to opt in. Pyodide's cold start can take a while in CI, so the tests use generous timeouts.
- The fixture app under `tests/e2e/app/` is Pyodide-runtime code (it uses absolute `app.*` imports that only resolve inside the Pyodide filesystem), so it's excluded from mypy and never imported by the CPython unit tests.

## Coverage

`pytest-cov` is in the `dev` group, and CI enforces a minimum:

```bash
uv run pytest -q --cov=wybthon --cov-branch --cov-report=term-missing
```

## Next steps

- Read the [Contributing guide](../meta/contributing.md) for the full local workflow.
- Browse the [Performance guide](performance.md) for benchmarking tips.
- See the [Pyodide guide](pyodide.md) for browser environment notes.
