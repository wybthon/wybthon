# Testing

Wybthon's reactive core, VDOM, reconciler, and event delegation are plain Python, so components can be tested in CPython with `pytest`, no browser required. [`wybthon.testing`][wybthon.testing] renders a view into an in-memory DOM through the real reconciler, kernel protocol, scheduler, and delegated events, then lets you query and interact with it the way a user would. Browser-specific behavior (real layout, Pyodide itself) is covered by a Playwright suite.

Two rules cover most of what's different about testing reactive code:

1. **Writes are staged.** After `set_count(1)`, `count()` still returns the old value until the graph flushes. In the browser that happens on a microtask; in a test, [`fire`][wybthon.testing.fire] flushes for you, and [`flush`][wybthon.flush] does it explicitly.
2. **Effects run after commit.** `create_effect`'s first run is deferred to the next flush, so assert after a flush.

## Rendering components

[`render`][wybthon.testing.render] mounts a view into a fresh container, flushes it, and returns a [`Screen`][wybthon.testing.Screen]:

```python
from wybthon import Prop, Props, component, create_signal, html
from wybthon.testing import fire, render


class CounterProps(Props):
    label: Prop[str]


@component
def Counter(props: CounterProps):
    count, set_count = create_signal(0)

    def increment():
        set_count(lambda n: n + 1)

    return html(t"""
      <div>
        <p>{props.label}: {count}</p>
        <button onclick={increment}>+</button>
      </div>
    """)


def test_counter_increments():
    with render(Counter(label="Clicks")) as screen:
        assert screen.get_by_text("Clicks: 0")
        fire.click(screen.get_by_role("button", name="+"))
        assert screen.get_by_text("Clicks: 1")
```

`render` accepts any node: a component call, an [`html`][wybthon.html] template, or a tree built with the element helpers. A template whose markup the browser would rewrite raises [`TemplateError`][wybthon.TemplateError] the first time it's used, so rendering a component in a test also checks its markup.

Use `render` as a context manager to unmount when the block ends, or call `screen.unmount()` yourself. `screen.html()` returns the container's inner HTML without Wybthon's comment markers, and `screen.text()` returns its text with whitespace collapsed:

```python
from wybthon import html
from wybthon.testing import render

with render(html(t"<ul><li>a</li><li>b</li></ul>")) as screen:
    assert screen.html() == "<ul><li>a</li><li>b</li></ul>"
    assert screen.text() == "ab"
```

### Cleaning up between tests

[`cleanup`][wybthon.testing.cleanup] unmounts every view that `render` mounted and that's still mounted. An autouse fixture in your `conftest.py` makes every test start from a clean slate, even when a test fails before it unmounts:

```python
import pytest

from wybthon.testing import cleanup


@pytest.fixture(autouse=True)
def _unmount_views():
    yield
    cleanup()
```

## Queries

Queries come in three forms, as in Testing Library:

| Form | No match | One match | Several matches |
| --- | --- | --- | --- |
| `get_by_*` | Raises `LookupError` | Returns it | Raises `LookupError` |
| `query_by_*` | Returns `None` | Returns it | Raises `LookupError` |
| `get_all_by_*` | Raises `LookupError` | Returns a list | Returns a list |

| Query | Finds |
| --- | --- |
| `get_by_text(text, exact=True)`, `query_by_text`, `get_all_by_text` | The deepest elements whose text matches. With `exact=False` the match is a case-insensitive substring; pass a compiled regular expression to search. |
| `get_by_role(role, name=None)`, `query_by_role`, `get_all_by_role` | Elements with an explicit `role` or an implicit one (`button`, `link`, `textbox`, `checkbox`, `heading`, `list`, ...). `name` matches the accessible name: `aria-label`, then the text content (or placeholder for inputs). |
| `get_by_label_text(text)`, `query_by_label_text` | The form control a `<label>` names (through `for` or by nesting), or the element with that `aria-label`. |
| `get_by_test_id(id)`, `query_by_test_id`, `get_all_by_test_id` | Elements whose `data-testid` matches. Write `data-testid="save"` in a template, or `data_testid="save"` with an element helper. |

Queries return [`TestNode`][wybthon.testing.TestNode]s. Read `.text_content`, `.attributes` (a dict of strings), `.value`, `.checked`, and `.tag`, or use `.classList.contains(name)`:

```python
import re

from wybthon import html
from wybthon.testing import render

form = html(t"""
  <div>
    <label for="email">Email</label>
    <input id="email" type="email" placeholder="you@example.com">
    <p data-testid="status">Saved 3 items</p>
    <button class="primary">Save</button>
  </div>
""")

with render(form) as screen:
    assert screen.get_by_label_text("Email").attributes["type"] == "email"
    assert screen.get_by_text(re.compile(r"Saved \d+ items"))
    assert screen.get_by_test_id("status").text_content == "Saved 3 items"
    assert screen.get_by_role("button", name="Save").classList.contains("primary")
    assert screen.query_by_text("Deleted") is None
```

## Firing events

[`fire`][wybthon.testing.fire] dispatches an event through Wybthon's delegated handlers, then flushes, so the next assertion sees the settled DOM:

| Helper | What it does |
| --- | --- |
| `fire.click(node)` | Dispatches `click`. |
| `fire.input(node, value)` | Sets the control's value, then dispatches `input`. |
| `fire.change(node, value=None, checked=None)` | Sets the value or checked state, then dispatches `change`. |
| `fire.submit(form)` | Dispatches `submit`. |
| `fire.key_down(node, key)` | Dispatches `keydown` with `key`. |
| `fire.focus(node)`, `fire.blur(node)` | Dispatch `focus` and `blur`. |
| `fire(node, "dblclick", **payload)` | Dispatches any event type. Keyword fields become event fields (`shift_key=True` is `e.shift_key`). |

```python
from wybthon import component, create_signal, html
from wybthon.testing import fire, render


@component
def Mirror():
    text, set_text = create_signal("")

    def update(e):
        set_text(e.target.value)

    return html(t"""
      <div>
        <input aria-label="Name" value={text} oninput={update}>
        <p>Hello, {text}</p>
      </div>
    """)


def test_input_updates_text():
    with render(Mirror()) as screen:
        fire.input(screen.get_by_label_text("Name"), "Ada")
        assert screen.get_by_text("Hello, Ada")
```

## Props and parents

Pass an accessor to drive a prop from the test, then [`flush`][wybthon.flush] after writing it. The component body runs once; only the bound text updates:

```python
from wybthon import Prop, Props, component, create_signal, flush, html
from wybthon.testing import render


class GreetingProps(Props):
    name: Prop[str]


runs: list[int] = []


@component
def Greeting(props: GreetingProps):
    runs.append(1)
    return html(t"<p>Hello, {props.name}</p>")


def test_prop_updates_without_rerunning_body():
    name, set_name = create_signal("Ada")
    with render(Greeting(name=name)) as screen:
        set_name("Grace")
        flush()
        assert screen.text() == "Hello, Grace"
        assert runs == [1]
```

Callbacks are plain fields, so a test can pass a recording function and assert on its calls after firing events.

## Async components

Async memos, actions, and `Loading` boundaries need an event loop. Run the test body with `asyncio.run` (or a plugin such as `pytest-asyncio`), and use [`wait_for`][wybthon.testing.wait_for] to wait for an observable result. It flushes between checks and raises `TimeoutError` if the condition never holds:

```python
import asyncio

from wybthon import Loading, component, create_memo, html
from wybthon.testing import render, wait_for


@component
def UserCard():
    async def load():
        await asyncio.sleep(0)
        return {"name": "Ada"}

    user = create_memo(load)

    def name():
        return user()["name"]

    return Loading(html(t"<p>User: {name}</p>"), fallback=html(t"<p>Loading...</p>"))


def test_loading_shows_fallback_then_content():
    async def main() -> None:
        with render(UserCard()) as screen:
            assert screen.text() == "Loading..."
            await wait_for(lambda: screen.query_by_text("User: Ada") is not None)

    asyncio.run(main())
```

[`tick`][wybthon.testing.tick] drains ready asyncio continuations and flushes, for when you want to step instead of wait. [`resolve`][wybthon.resolve] awaits an async memo's next settled value: `assert await resolve(user) == {"name": "Ada"}`.

## The reactive core, no DOM

Signals, memos, effects, and stores need no rendering at all. [`reactive_scope`][wybthon.testing.reactive_scope] owns the computations created inside it and disposes them when the block ends:

```python
from wybthon import create_effect, create_memo, create_signal, flush
from wybthon.testing import reactive_scope


def test_memo_and_effect():
    with reactive_scope():
        count, set_count = create_signal(0)
        doubled = create_memo(lambda: count() * 2)
        seen: list[int] = []

        create_effect(doubled, lambda value, prev: seen.append(value))
        flush()  # first effect run
        assert seen == [0]

        set_count(1)
        set_count(lambda n: n + 1)  # functional updates compose
        assert count() == 0  # still staged
        flush()
        assert count() == 2
        assert seen == [0, 4]  # one effect run per flush
```

### Stores, router, and forms

- Store writes are staged like signal writes. Python doesn't allow assignment inside a lambda, so write draft functions with `def`, pass them to the setter, and flush before asserting on reads.
- Outside a browser, [`navigate`][wybthon.router.navigate] only updates the `current_path` signal. Flush afterward. Path matching ([`resolve`][wybthon.router.resolve] in `wybthon.router`) is pure and needs no rendering.
- Drive form bindings with `fire.input`, `fire.change`, and `fire.submit` against the rendered controls.

### Dev-mode diagnostics

Dev-mode warnings print to `stderr`; capture them with pytest's `capsys`. Warnings are deduplicated per process, so call `wybthon._warnings._reset_warning_dedupe()` at the start of a test that asserts on one. A write inside a memo raises `WriteInScopeError` when the memo is read (`pytest.raises(WriteInScopeError)` around the read); a write inside a single-function effect surfaces through the effect's `error=` handler on the next flush. Calling a component with an unknown or missing prop raises `TypeError` at the call.

## Framework tests

Wybthon's own unit tests under `tests/` also use a lower-level `wyb` fixture from `tests/conftest.py`. It installs stub `js` and `pyodide` modules, reloads the browser-facing modules (`kernel`, `dom`, `events`, `reconciler`, `_shapes`), and installs a `kernel.PythonBackend` over the same in-memory document `wybthon.testing` uses; `root_element` provides a fresh container. Use it when a test needs to inspect kernel commands or reconciler internals. For component behavior, prefer `wybthon.testing`.

Run the unit suite with:

```bash
uv run pytest -q
```

## Browser E2E suite (Playwright and Pyodide)

The `e2e` job in CI runs the browser suite under `tests/e2e/`. All tests carry the `e2e` pytest marker and exercise the real Pyodide runtime (314.0.6) in headless Chromium against a **feature fixture app**: an ordinary `wybthon.toml` project in `tests/e2e/` with one route per framework feature (reactivity, holes, props, events, context, flow control, forms, stores, loading, error boundaries, lifecycle, portal, lazy loading, router, hydration, and production builds). Each per-feature test module (`tests/e2e/test_*.py`) drives that route and asserts through stable `data-testid` selectors.

Design choices that keep the suite fast and deterministic:

- **Boot Pyodide once.** The session-scoped fixture starts `wyb dev --dir tests/e2e` and boots the app a single time; tests navigate between features with the History API router instead of reloading the page.
- **Isolation between tests.** The `goto_feature` helper bounces through a `/blank` route first, forcing the previous feature's tree to unmount.
- **Stable selectors.** Components expose `data-testid` attributes (see the `tid` helper in `tests/e2e/app/testkit.py`).
- **Fail fast on boot errors.** The bootstrap records its status on `window.__WYB.status`, and the readiness wait surfaces a boot error as a test error instead of a timeout. The page's Pyodide instance is `window.__WYB.pyodide`, and the app mounts into `#app`.

Run locally:

```bash
uv sync --group dev
uv run playwright install chromium

# full browser suite
uv run pytest -q -m e2e tests/e2e

# a single feature module
uv run pytest -q -m e2e tests/e2e/test_errors.py
```

Notes:

- The default pytest configuration excludes the browser suite from the fast unit run; pass `-m e2e` to opt in. Pyodide's cold start can take a while in CI, so the tests use generous timeouts.
- The fixture app under `tests/e2e/app/` is Pyodide-runtime code (it uses absolute `app.*` imports that only resolve inside the built bundle), so it's excluded from mypy and never imported by the CPython unit tests.

## Coverage

`pytest-cov` is in the `dev` group, and CI fails below 80% coverage:

```bash
uv run pytest -q --cov=wybthon --cov-branch --cov-report=term-missing --cov-fail-under=80
```

## Next steps

- Read the [Contributing guide](../meta/contributing.md) for the full local workflow.
- Browse the [Performance guide](performance.md) for benchmarking tips.
- See the [`testing`][wybthon.testing] API reference for every query and helper.
