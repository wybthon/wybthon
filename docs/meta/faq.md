# FAQ

Quick answers to the questions we get most often. If yours isn't here, check the [troubleshooting guide](troubleshooting.md) or open an issue.

## General

??? question "Is Wybthon production ready?"

    Not yet. The framework is pre-1.0 and the public API may shift between minor releases (old APIs are removed outright rather than shimmed). We recommend it for prototypes, internal tools, and learning projects today, and we'll relax this guidance as the API stabilizes.

??? question "Does it work outside the browser?"

    Everything except the real browser. Signals, memos, effects, async computations, actions, stores, forms, context, flow control, and VDOM construction run in plain CPython. [`wybthon.testing`][wybthon.testing] renders components into an in-memory DOM through the real reconciler and event delegation, so you can test them with `pytest` (see the [testing guide](../guides/testing.md)), and [`wybthon.server`][wybthon.server] renders them to HTML for prerendering and server rendering.

??? question "Which Python version do I need?"

    Python 3.14. Template strings (PEP 750) are part of the component API, and server rendering, tests, and tooling run on the same Python version as the browser. In the browser that means Pyodide 314 or newer; `wyb init` pins 314.0.6.

??? question "Why Python in the browser?"

    Wybthon lets data scientists, researchers, and tooling teams build interactive UIs without switching to TypeScript. Pyodide makes the scientific Python stack (NumPy, pandas, scikit-learn, and friends) available client-side, so you can render results without a server round-trip.

??? question "Why is there a virtual DOM if this is 'SolidJS for Python'?"

    Python has no JSX compiler to split static markup from dynamic parts, and every DOM call crosses the Python-to-JavaScript bridge. The VDOM is a rendering implementation detail: each reactive hole diffs only its own subtree, and the reconciler batches the resulting mutations through a JavaScript kernel in one bridge crossing. The reactive model is still fine-grained; a signal change re-runs the holes that read it, never whole components.

## Pyodide and runtime

??? question "Which Pyodide version should I target?"

    Pin a single version per deployment with `pyodide-version` in `wybthon.toml`. Wybthon requires Pyodide 314 or newer (Python 3.14). Building with the same Python version as the runtime also lets `wyb build` ship precompiled bytecode.

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

    There's no JavaScript bundler, but there is a build step. `wyb build` packages Wybthon and your application into archives with a generated bootstrap, prerenders the routes you list, and turns dev mode off; any static host can serve the result. `wyb dev` runs the same build in development mode and reloads on change. See the [deployment guide](../guides/deployment.md).

??? question "Can I lazy-load route components?"

    Yes; see [`lazy`][wybthon.lazy]. It's backed by an async memo, so it integrates with [`Loading`][wybthon.Loading] for declarative loading UIs and with [`Errored`][wybthon.Errored] for load failures, and each lazy component has a `.preload()` method for warming the cache early.

## Components and props

??? question "How do I declare a component's props?"

    Subclass [`Props`][wybthon.Props] and take one parameter annotated with it. `Prop[T]` fields are reactive; anything else is a plain field:

    ```python
    from collections.abc import Callable

    from wybthon import Prop, Props, button, component, prop


    class SaveButtonProps(Props):
        label: Prop[str] = prop(default="Save")
        on_save: Callable[[], None] | None = None


    @component
    def SaveButton(props: SaveButtonProps):
        return button(props.label, on_click=props.on_save)
    ```

    A component with no inputs takes no parameters. See [Authoring patterns](../guides/authoring-patterns.md#declaring-props).

??? question "How do I pass a callback to a component?"

    Declare it as a plain field, such as `on_save: Callable[[], None] | None = None`. Reading `props.on_save` returns the function exactly as the parent passed it, and nothing calls it for you. Only `Prop[T]` fields are reactive.

??? question "Why does my type checker reject `prop(0)`?"

    Defaults must be passed by keyword: `prop(default=0)`, or `prop(default_factory=list)` for a mutable value. Type checkers only recognize a field default given by keyword. Plain fields use ordinary defaults (`= None`).

??? question "How do I pass children?"

    Subclass [`ParentProps`][wybthon.ParentProps] and place `props.children` in the tree. Callers use item syntax, `Card(title="Hi")[p("Body")]`, or the `children=` keyword.

??? question "Do I need a mypy plugin?"

    No. `Props` uses PEP 681 `dataclass_transform`, so pyright, Pylance, and mypy check component calls out of the box. See the [typing guide](../guides/typing.md).

??? question "Where did `Router`, `Link`, and `form_state` go?"

    The core lives in `wybthon`; the router, forms, virtual lists, and scheduling helpers live in their own modules. Import them from `wybthon.router`, `wybthon.forms`, `wybthon.virtual`, and `wybthon.scheduling`:

    ```python
    from wybthon.forms import bind_text, form_state
    from wybthon.router import Link, Route, Router, navigate
    ```

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
    flush()  # the name effect runs once, not twice
    ```

    There is no `batch()` function.

??? question "Why didn't my effect run when I created it?"

    [`create_effect`][wybthon.create_effect] runs its first time on the next flush, after the DOM has been committed, so an effect created in a component body sees the mounted DOM. If you need code to run immediately during setup, just run it; if you need something after mount, use [`on_settled`][wybthon.on_settled]. [`create_render_effect`][wybthon.create_render_effect] runs immediately, but it's meant for rendering primitives.

??? question "How do I fetch data?"

    Write an `async def` and pass it to [`create_memo`][wybthon.create_memo]. Reads before the first value raise [`NotReadyError`][wybthon.NotReadyError], which the nearest [`Loading`][wybthon.Loading] boundary turns into fallback UI; later refetches run as transitions that hold the dependent UI on the previous state until the new value lands. Use [`is_pending`][wybthon.is_pending] for a refresh hint, [`latest`][wybthon.latest] to peek without suspending, and [`refresh`][wybthon.refresh] or [`resolve`][wybthon.resolve] to drive it imperatively. Mutations go through [`action`][wybthon.action], optionally with [`create_optimistic`][wybthon.create_optimistic] for instant UI.

??? question "How do I highlight the selected row without re-running every row?"

    Use a projection keyed by the selection. Each row reads only its own key, so a change notifies the old and new rows:

    ```python
    from wybthon import create_projection, create_signal

    selected, set_selected = create_signal(None)
    is_selected = create_projection(lambda: {} if selected() is None else {selected(): True})
    # In a row: class_=lambda: "active" if is_selected.get(row_id) else ""
    ```

??? question "Why don't I see dev warnings in production?"

    `wyb build` turns dev mode off before your application imports, so production builds skip development checks and warnings. `wyb dev` keeps them on. Check the mode with [`is_dev_mode()`][wybthon.is_dev_mode].

## Next steps

- New here? Read [Getting started](../getting-started.md).
- Looking for something to build? Browse the [examples](../examples.md).
- Hit an unexpected error? Try the [troubleshooting guide](troubleshooting.md).
