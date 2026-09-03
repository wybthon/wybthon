# FAQ

Quick answers to the questions we get most often. If yours isn't here, check the [troubleshooting guide](troubleshooting.md) or open an issue.

## General

??? question "Is Wybthon production ready?"

    Not yet. The framework is pre-1.0 and the public API may shift between minor releases (old APIs are removed outright rather than shimmed). We recommend it for prototypes, internal tools, and learning projects today, and we'll relax this guidance as the API stabilizes.

??? question "Does it work outside the browser?"

    Everything except the real DOM. Signals, memos, effects, async computations, actions, stores, forms, context, flow control, and VDOM construction run in plain CPython and are tested with `pytest`. Rendering into a page, `Element` queries, and history navigation need Pyodide, or the stub backend the unit tests use (see the [testing guide](../guides/testing.md)).

??? question "Which Python version do I need?"

    Python 3.12 or newer in CPython (the framework uses PEP 695 generics such as `Accessor[T]`). In the browser, Pyodide 0.27 or newer (Python 3.12); the E2E suite pins Pyodide 314.x.

??? question "Why Python in the browser?"

    Wybthon lets data scientists, researchers, and tooling teams build interactive UIs without switching to TypeScript. Pyodide makes the scientific Python stack (NumPy, pandas, scikit-learn, and friends) available client-side, so you can render results without a server round-trip.

??? question "Why is there a virtual DOM if this is 'SolidJS for Python'?"

    Python has no JSX compiler to split static markup from dynamic parts, and every DOM call crosses the Python-to-JavaScript bridge. The VDOM is a rendering implementation detail: each reactive hole diffs only its own subtree, and the reconciler batches the resulting mutations through a JavaScript kernel in one bridge crossing. The reactive model is still fine-grained; a signal change re-runs the holes that read it, never whole components.

## Pyodide and runtime

??? question "Which Pyodide version should I target?"

    Pin a single version per deployment. Wybthon requires Pyodide 0.27 or newer, the first release with Python 3.12; using the same version locally and in production avoids subtle ABI mismatches.

??? question "How do I install Python packages from PyPI?"

    Use [`micropip`](https://micropip.pyodide.org/) inside Pyodide:

    ```python
    import micropip

    async def setup():
        await micropip.install("httpx")
    ```

    The package must be pure Python or available as a Pyodide-compatible wheel. See the [Pyodide guide](../guides/pyodide.md) for details.

??? question "How do I call a JavaScript API from Python?"

    Import names from the [`js` module](https://pyodide.org/en/stable/usage/api/python-api/ffi.html#module-js) yourself (Wybthon doesn't re-export it):

    ```python
    from js import fetch, window

    window.alert("hello!")

    async def load_users():
        response = await fetch("/api/users")
        return await response.json()
    ```

    Convert Python objects with `pyodide.ffi.to_js(...)` when handing them to JS APIs that expect plain objects. For DOM nodes Wybthon rendered, prefer [`Ref`][wybthon.Ref] and [`Element`][wybthon.Element] over `document.querySelector`.

## Building and shipping apps

??? question "Do I need a bundler or a build step?"

    No. Wybthon serves Python source files directly via the dev server (`wyb dev --dir .`) and any static host can serve them in production. See the [deployment guide](../guides/deployment.md) for hosting recipes.

??? question "Can I lazy-load route components?"

    Yes; see [`lazy`][wybthon.lazy]. It's backed by an async memo, so it integrates with [`Loading`][wybthon.Loading] for declarative loading UIs and with [`Errored`][wybthon.Errored] for load failures, and each lazy component has a `.preload()` method for warming the cache early.

## Reactivity

??? question "Why didn't my component re-run after a signal changed?"

    Because components run **once** by design. A read in the component body captures the value at setup time. To stay reactive, place the accessor itself in the rendered tree (`span(my_signal)`), wrap the expression in a zero-arg lambda (`span(lambda: f"{count()} items")`), or derive it with [`create_memo`][wybthon.create_memo]. In dev mode Wybthon warns when a signal, memo, or prop is read at the top level of a component body; use `.peek()` when a one-time read is what you want.

??? question "Why does my signal still show the old value right after I set it?"

    Writes are **staged**. `set_count(1)` records the new value, and `count()` keeps returning the committed value until the next flush: a browser microtask, the end of an event handler, or an explicit [`flush`][wybthon.flush]. Functional updates see the staged value, so `set_count(lambda n: n + 1)` twice in one handler adds two. In tests and plain scripts, call `flush()` after your writes before asserting.

??? question "How do I batch multiple signal updates?"

    You don't need to; everything batches. Consecutive writes in one handler (or one synchronous block) coalesce into a single flush, so an effect that reads both fields runs once:

    ```python
    set_first("Ada")
    set_last("Lovelace")
    flush()   # the name effect runs once, not twice
    ```

    There is no `batch()` function.

??? question "Why didn't my effect run when I created it?"

    [`create_effect`][wybthon.create_effect] runs its first time on the next flush, after the DOM has been committed, so an effect created in a component body sees the mounted DOM. If you need code to run immediately during setup, just run it; if you need something after mount, use [`on_settled`][wybthon.on_settled]. [`create_render_effect`][wybthon.create_render_effect] runs immediately, but it's meant for rendering primitives.

??? question "How do I fetch data?"

    Write an `async def` and pass it to [`create_memo`][wybthon.create_memo]. Reads before the first value raise [`NotReadyError`][wybthon.NotReadyError], which the nearest [`Loading`][wybthon.Loading] boundary turns into fallback UI; later refetches keep serving the stale value while revalidating. Use [`is_pending`][wybthon.is_pending] for a refresh hint, [`latest`][wybthon.latest] to peek without suspending, and [`refresh`][wybthon.refresh] or [`resolve`][wybthon.resolve] to drive it imperatively. Mutations go through [`action`][wybthon.action], optionally with [`create_optimistic`][wybthon.create_optimistic] for instant UI.

## Next steps

- New here? Read [Getting started](../getting-started.md).
- Looking for something to build? Browse the [examples](../examples.md).
- Hit an unexpected error? Try the [troubleshooting guide](troubleshooting.md).
