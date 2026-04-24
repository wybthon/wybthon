# FAQ

Quick answers to the questions we get most often. If yours isn't here, check the [troubleshooting guide](troubleshooting.md) or open an issue.

## General

??? question "Is Wybthon production ready?"

    Not yet. The framework is experimental (pre-alpha) and the public API may shift between releases. We recommend it for prototypes, internal tools, and learning projects today, and we'll relax this guidance as the API stabilizes.

??? question "Does it work outside the browser?"

    The core reactive primitives ([`create_signal`][wybthon.create_signal], [`create_effect`][wybthon.create_effect], stores) work in plain CPython and are tested with `pytest`. Rendering, DOM, and event APIs require Pyodide because they call into the browser's `document`, `window`, and friends.

??? question "Why Python in the browser?"

    Wybthon lets data scientists, researchers, and tooling teams build interactive UIs without context-switching to TypeScript. Pyodide makes the entire scientific Python stack (NumPy, pandas, scikit-learn, etc.) available client-side, so you can render results without a server round-trip.

## Pyodide & runtime

??? question "Which Pyodide version should I target?"

    Pin a single version per deployment. Wybthon tracks the latest stable Pyodide release (currently the 0.27 series); using the same version locally and in production avoids subtle ABI mismatches.

??? question "How do I install Python packages from PyPI?"

    Use [`micropip`](https://micropip.pyodide.org/) inside Pyodide:

    ```python
    import micropip
    await micropip.install("httpx")
    ```

    The package must be either pure-Python or available as a Pyodide-compatible wheel. See the [Pyodide guide](../guides/pyodide.md) for details.

??? question "How do I call a JavaScript API from Python?"

    Import names from the magic [`js` module](https://pyodide.org/en/stable/usage/api/python-api/ffi.html#module-js):

    ```python
    from js import window, fetch

    window.alert("hello!")
    response = await fetch("/api/users")
    ```

    Convert Python objects with `pyodide.ffi.to_js(...)` when handing them to JS APIs that expect plain objects.

## Building & shipping apps

??? question "Do I need a bundler or a build step?"

    No. Wybthon serves Python source files directly via the dev server (`wyb dev --dir .`) and any static host can serve them in production. See the [deployment guide](../guides/deployment.md) for hosting recipes.

??? question "Can I lazy-load route components?"

    Yes — see [`lazy`][wybthon.lazy] and [`load_component`][wybthon.load_component]. Combine them with [`Suspense`][wybthon.Suspense] for declarative loading UIs.

## Reactivity

??? question "Why didn't my component re-run after a signal changed?"

    Because Wybthon's components run **once** by design. Reads inside the component body capture the value at setup time. To stay reactive, place signal accessors inside the rendered tree (`span(my_signal)`) or wrap them in [`dynamic(lambda: ...)`][wybthon.dynamic]. The framework prints a dev-mode warning when it detects a destructured prop access (see `warn_destructured_prop` in `wybthon._warnings`).

??? question "How do I batch multiple signal updates?"

    Wrap them in [`batch`][wybthon.batch]:

    ```python
    from wybthon import batch

    with_batch = batch(lambda: (set_first("Ada"), set_last("Lovelace")))
    ```

    Effects only run once after the batch resolves.

## Next steps

- New here? Read [Getting started](../getting-started.md).
- Looking for something to build? Browse the [examples](../examples.md).
- Hit an unexpected error? Try the [troubleshooting guide](troubleshooting.md).
