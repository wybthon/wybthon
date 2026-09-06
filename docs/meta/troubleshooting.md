# Troubleshooting

If something isn't working as expected, scan this page for the symptom you're seeing. Each entry includes the most likely cause and a fix; expand for more detail.

## Setup

??? bug "`SyntaxError` or `TypeError` on import under an older Python"

    **Symptoms:** importing `wybthon` in CPython fails with a syntax error mentioning `class Accessor[T]` or `type Validator = ...`, or `pip` refuses to install.

    **Likely cause:** Wybthon requires Python 3.12 or newer (PEP 695 generics and the `type` statement). In the browser that means Pyodide 0.27 or newer (Python 3.12).

    **Fix:** upgrade the interpreter (`uv python install 3.12` works well) and re-create your virtual environment. Pin a Pyodide release that ships Python 3.12+ in `index.html`.

??? bug "Pyodide fails to load"

    **Symptoms:** the page renders nothing; the browser console shows a network error or an `Importing pyodide failed` message.

    **Likely causes:**

    - The CDN URL referenced from your `index.html` is unreachable (offline development, corporate firewall, ad blocker).
    - You bumped the Pyodide version but the matching `pyodide.js` and `pyodide.asm.wasm` files weren't refreshed together.

    **Fix:**

    1. Check the network tab and confirm the Pyodide assets return `200`.
    2. Try loading from a local copy by self-hosting the Pyodide release that matches your `pyodide.js` URL.
    3. If using a corporate CDN, allowlist the Pyodide host(s) and the `*.wasm` content type.

??? bug "`mkdocs build --strict` fails after updating docs"

    **Symptoms:** the docs site builds locally with `mkdocs serve` but `mkdocs build --strict` fails.

    **Likely cause:** an unresolved cross-reference (for example a typo in a `[label][wybthon.symbol]` link, or a link to a name that was removed in the API overhaul) or an unused `nav` entry.

    **Fix:** read the warning text. `mkdocstrings` reports the exact symbol it couldn't find, so update the page or the symbol's docstring accordingly. If the broken link is intentional (for example, while a feature is in flight), turn the link into plain text or remove it.

## Reactive bugs

??? bug "`WriteInScopeError: Cannot write a signal inside a tracking scope`"

    **Symptoms:** a `WriteInScopeError` is raised from a `set_*` call made inside a memo body, a `create_tracked_effect`, a reactive hole (a lambda in the tree), or a store setter called from one of those.

    **Likely cause:** writing a signal from a tracking scope is almost always a bug: it either creates a feedback loop or hides a value that should be derived.

    **Fix:** derive the value with [`create_memo`][wybthon.create_memo] (or [`create_projection`][wybthon.create_projection] for stores) instead of writing it, or move the write into the untracked `apply` stage of a split effect, `create_effect(compute, apply)`, an event handler, or an [`action`][wybthon.action]. The check only runs in dev mode, but leaving the write in place means the bug ships silently; fix it rather than calling `set_dev_mode(False)`.

??? bug "A component reads a prop or signal but doesn't update"

    **Symptoms:** the console shows `[wybthon] Warning: Component <X> read reactive value prop '<name>' at the top level of its body.` during the first render, and the value never changes afterwards.

    **Likely cause:** you called `my_prop()` or `count()` in the component body before returning the tree. Components run once, so that read isn't tracked and its value is frozen.

    **Fix:** put the accessor itself in the tree (`span(my_prop)`), wrap the expression in a zero-arg lambda (`span(lambda: my_prop().upper())`), or derive it with `create_memo`. If a one-time read is what you want (seeding local state, for example), make it explicit with `my_prop.peek()` or [`untrack`][wybthon.untrack]; both silence the warning.

??? bug "My signal read shows the old value right after I set it"

    **Symptoms:** `set_count(1); assert count() == 1` fails; `count()` still returns `0`.

    **Likely cause:** writes are **staged**. The setter records the new value, and reads return the committed value until the next flush. In the browser that happens automatically (a microtask, and at the end of every event handler), but synchronous test code observes the state before the flush.

    **Fix:** call [`flush`][wybthon.flush] after your writes in tests and scripts. Inside a handler, use a functional update (`set_count(lambda n: n + 1)`) when the next write depends on the previous one; updaters see the staged value.

??? bug "My effect didn't run when I created it"

    **Symptoms:** `create_tracked_effect(lambda: print(count()))` prints nothing until something changes (or until you call `flush()`).

    **Likely cause:** the first run of [`create_effect`][wybthon.create_effect] is deferred to the effect phase of the next flush, after the DOM commit, so effects created in a component body observe the mounted DOM.

    **Fix:** in tests, call `flush()` after creating the effect. In components, this is the behavior you want; use [`on_settled`][wybthon.on_settled] for one-time post-mount work and `.peek()` for a synchronous read during setup.

??? bug "`NotReadyError: Async computation has no value yet`"

    **Symptoms:** calling an async memo (one whose body is `async def`) from an event handler, a component body, or plain script code raises `NotReadyError`. Or, in the tree, a hole that reads the memo renders nothing and no loading indicator appears.

    **Likely cause:** the read happened before the memo produced its first value. Inside a hole, memo, or effect the framework handles this: the reader stays pending and the nearest [`Loading`][wybthon.Loading] boundary shows its fallback. Without a `Loading` above it, the hole simply stays empty until the value arrives; outside any tracking scope the exception surfaces to your code.

    **Fix:** wrap the consuming subtree in `Loading(..., fallback=...)`. To read from imperative code, use [`latest`][wybthon.latest] (returns the stale value or `None`), guard with [`is_pending`][wybthon.is_pending], or `await resolve(memo)` in async code.

??? bug "`ContextNotFoundError` from `use_context`"

    **Symptoms:** `use_context(Theme)` raises `ContextNotFoundError: use_context(Context(Theme)) found no provider above the caller and the context has no default.`

    **Likely causes:**

    - The provider isn't an ancestor in the *reactive* tree: `Theme(value, *children)` must wrap the component that reads it.
    - `use_context` was called outside any reactive scope (module level, or after an `await` without restoring the owner).
    - The context was created without a default.

    **Fix:** move the provider above the reader; capture [`get_owner`][wybthon.get_owner] before an `await` and call `use_context` inside [`run_with_owner`][wybthon.run_with_owner]; or pass a `default=` to [`create_context`][wybthon.create_context] when a missing provider is acceptable.

??? bug "`For` rendered once and never updated"

    **Symptoms:** the list renders correctly the first time, then stops responding to updates. The console shows `[wybthon] Warning: For received a plain list for `each=`.`

    **Likely cause:** you passed a Python list instead of an accessor for `each`.

    **Fix:** pass the accessor (the getter from [`create_signal`][wybthon.create_signal], a memo, or a store list) so the list reacts to updates. If the row callback needs the item to be live, use `keyed=False` or a key function so it receives an item accessor.

??? bug "An effect fires forever or `reactive update did not stabilize`"

    **Symptoms:** the browser freezes, or a `RuntimeError: Wybthon: reactive update did not stabilize` is raised from `flush()`.

    **Likely cause:** an effect writes a signal it also reads, so every flush dirties it again.

    **Fix:** split the effect into `create_effect(compute, apply)` so the write happens in the untracked `apply` stage against a value that doesn't feed back, or replace the effect with a memo.

## DOM and events

??? bug "Click handler never fires"

    **Symptoms:** no console log, no state change.

    **Likely causes:**

    - The prop name is misspelled. Wybthon expects `on_click`, `on_input`, `on_change`, and so on (`onClick` also works).
    - The event type doesn't bubble (`focus`, `blur`, `mouseenter`, `scroll`); delegation only sees bubbling events.
    - The element lives outside every container passed to [`render`][wybthon.render] (for example a [`Portal`][wybthon.Portal] mounted into `body`), so no delegation root receives the event.
    - The handler returns a coroutine without scheduling it; nothing happens but no error is raised.

    **Fix:** confirm the prop name, switch to a bubbling type (`focusin`, `mouseover`) or attach a native listener through a [`Ref`][wybthon.Ref] in [`on_settled`][wybthon.on_settled], keep portal targets inside a render container, and schedule async handlers with `asyncio.create_task(...)` or wrap them in an [`action`][wybthon.action].

??? bug "`ref.current` is `None` when I read it"

    **Symptoms:** `ref.current` is `None` inside the component body, but works inside a click handler.

    **Likely cause:** you read the ref before the element mounted.

    **Fix:** read the ref inside [`on_settled`][wybthon.on_settled], an effect, or an event handler; all of them run after the first commit.

??? bug "A boolean attribute renders as `disabled=\"false\"`"

    **Symptoms:** the element stays disabled even though you passed `False`.

    **Likely cause:** you passed the string `"false"` rather than the boolean.

    **Fix:** pass a real boolean or an accessor returning one. `True` sets the attribute, `False` or `None` removes it; see [props](../api/props.md).

## Dev server

??? bug "SSE reloads not firing"

    **Symptoms:** edits to source files don't trigger a browser refresh.

    **Likely causes:**

    - The dev server isn't running, or you started it from a different directory.
    - A reverse proxy in front of the dev server buffers responses and breaks the persistent `/__sse` connection.

    **Fix:** ensure `wyb dev` is active, that `/__sse` returns `text/event-stream`, and that any proxy you use supports HTTP/1.1 streaming.

??? bug "Files served as `text/plain` instead of `text/x-python`"

    **Symptoms:** Pyodide can't import your modules in production; the browser console shows a content-type warning.

    **Fix:** configure your static host to serve `.py` files as `text/x-python` (see the [deployment guide](../guides/deployment.md) for Netlify, Vercel, and GitHub Pages snippets).

## When all else fails

- Re-run `python -m pytest tests -q` to confirm the framework itself still works in your environment.
- Capture a minimal reproduction and [open an issue](https://github.com/wybthon/wybthon/issues/new).
- Toggle [`set_dev_mode(False)`][wybthon.set_dev_mode] only after you've confirmed the warnings aren't pointing at a real bug.

## Next steps

- Skim the [FAQ](faq.md) for common questions.
- Read [Reactivity](../concepts/reactivity.md) for a refresher on signals, effects, and reactive holes.
- See the [testing guide](../guides/testing.md) for driving flushes and events in CPython.
