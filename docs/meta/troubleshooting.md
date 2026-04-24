# Troubleshooting

If something isn't working as expected, scan this page for the symptom you're seeing. Each entry includes the most likely cause and a fix; expand for more detail.

## Setup

??? bug "Pyodide fails to load"

    **Symptoms:** the page renders nothing; the browser console shows a network error or an `Importing pyodide failed` message.

    **Likely causes:**

    - The CDN URL referenced from your `index.html` is unreachable (offline development, corporate firewall, ad-blocker).
    - You bumped the Pyodide version but the matching `pyodide.js` and `pyodide.asm.wasm` files weren't refreshed together.

    **Fix:**

    1. Check the network tab and confirm the Pyodide assets return `200`.
    2. Try loading from a local copy by self-hosting the Pyodide release that matches your `pyodide.js` URL.
    3. If using a corporate CDN, allowlist the Pyodide host(s) and the `*.wasm` content type.

??? bug "`mkdocs build --strict` fails after updating docs"

    **Symptoms:** the docs site builds locally with `mkdocs serve` but `mkdocs build --strict` fails.

    **Likely cause:** an unresolved cross-reference (for example a typo in a `[label][wybthon.symbol]` link) or an unused `nav` entry.

    **Fix:** read the warning text. `mkdocstrings` reports the exact symbol it could not find, so update the page or the symbol's docstring accordingly. If the broken link is intentional (e.g., while a feature is in flight), turn the link into plain text or remove it.

## Reactive bugs

??? bug "A component reads a prop but doesn't update when the parent changes it"

    **Symptoms:** Wybthon prints a `[wybthon] Warning: Component <X> unwrapped prop '<name>' during setup.` warning during the first render.

    **Likely cause:** you called `my_prop()` in the component body before returning the VNode tree, freezing the value in a closure.

    **Fix:** pass the accessor itself into the rendered tree (`span(my_prop)`) or wrap dependent expressions in [`dynamic(lambda: ...)`][wybthon.dynamic]. See `warn_destructured_prop` in `wybthon._warnings` for the full explanation.

??? bug "`For` or `Index` rendered once and never updated"

    **Symptoms:** the list renders correctly the first time, then stops responding to updates. The console shows `[wybthon] Warning: <For> received a plain list for `each=`.`

    **Likely cause:** you passed a Python list instead of a signal accessor for `each=`.

    **Fix:** make `each` a signal accessor (typically the getter returned by [`create_signal`][wybthon.create_signal]) so the list reacts to updates. See `warn_each_plain_list` in `wybthon._warnings`.

??? bug "An effect fires more often than expected"

    **Symptoms:** a side-effect (network request, log line, etc.) runs multiple times when you only expected one trigger.

    **Likely cause:** the effect reads several signals that all change inside the same event handler. Without batching, each `set` call schedules another flush.

    **Fix:** wrap the updates in [`batch`][wybthon.batch] so they coalesce into a single update.

## DOM and events

??? bug "Click handler never fires"

    **Symptoms:** no console log, no state change.

    **Likely causes:**

    - The prop name is misspelled. Wybthon expects `on_click`, `on_input`, `on_change`, etc.
    - The element is covered by another element with `pointer-events: auto`.
    - The handler returns a coroutine without scheduling it; nothing happens but no error is raised.

    **Fix:** confirm the prop name (Wybthon does not coerce `onclick` to `on_click`), inspect the DOM tree for overlays, and ensure async handlers are scheduled with `asyncio.create_task(...)` if they should run.

??? bug "`ref.current` is `None` when I read it"

    **Symptoms:** `ref.current` is `None` inside the component body, but works inside a click handler.

    **Likely cause:** you read the ref before the element mounted.

    **Fix:** read the ref inside [`on_mount`][wybthon.on_mount], an effect, or an event handler; all of which run after the first commit.

## Dev server

??? bug "SSE reloads not firing"

    **Symptoms:** edits to source files don't trigger a browser refresh.

    **Likely causes:**

    - The dev server isn't running, or you started it from a different directory.
    - A reverse proxy in front of the dev server buffers responses and breaks the persistent `/__sse` connection.

    **Fix:** ensure `wyb dev` is active, that `/__sse` returns `text/event-stream`, and that any proxy you use supports HTTP/1.1 streaming.

??? bug "Files served as `text/plain` instead of `text/x-python`"

    **Symptoms:** Pyodide can't import your modules in production; the browser console shows a content-type warning.

    **Fix:** configure your static host to serve `.py` files as `text/x-python` (see the [deployment guide](../guides/deployment.md) for Netlify/Vercel/GitHub Pages snippets).

## When all else fails

- Re-run `python -m pytest` to confirm the framework itself still works in your environment.
- Capture a minimal reproduction (preferably under `examples/`) and [open an issue](https://github.com/wybthon/wybthon/issues/new).
- Toggle `set_dev_mode(False)` (from `wybthon._warnings`) only after you've confirmed the warnings are not pointing at a real bug.

## Next steps

- Skim the [FAQ](faq.md) for common questions.
- Read [Reactivity](../concepts/reactivity.md) for a refresher on signals, effects, and reactive holes.
