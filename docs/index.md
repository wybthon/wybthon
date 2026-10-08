# Wybthon

Wybthon is SolidJS for Python: a client-side single-page application (SPA) framework with SolidJS 2.0's fine-grained reactive model, a Pythonic API, and a runtime that lives in the browser through [Pyodide](https://pyodide.org/).

If you can write Python, you can build interactive web apps with Wybthon. There's no JavaScript build pipeline and no JSX.

## What is Wybthon?

You write function components in Python, return a tree built from HTML helpers, and drop signals, memos, and small reactive expressions into that tree. Components run **once**. When a signal changes, only the reactive holes that read it re-run, and the reconciler batches the resulting DOM mutations into a single crossing of the Python-to-JavaScript bridge.

The framework ships with everything you need to build a real app:

- Reactive primitives: [`create_signal`][wybthon.create_signal], [`create_memo`][wybthon.create_memo], and [`create_effect`][wybthon.create_effect], with automatic batching and typed accessors.
- Async-first data: an `async def` passed to `create_memo` is the fetching primitive; [`Loading`][wybthon.Loading] and [`Errored`][wybthon.Errored] boundaries handle the pending and failure states.
- [`action`][wybthon.action] with [`create_optimistic`][wybthon.create_optimistic] and [`create_optimistic_store`][wybthon.create_optimistic_store] for mutations.
- Draft-first stores ([`create_store`][wybthon.create_store], [`reconcile`][wybthon.reconcile], [`create_projection`][wybthon.create_projection]).
- Flow control ([`Show`][wybthon.Show], [`For`][wybthon.For], [`Repeat`][wybthon.Repeat], [`Switch`][wybthon.Switch], [`dynamic`][wybthon.dynamic]), callable [`Context`][wybthon.Context] objects, [`Portal`][wybthon.Portal], and [`lazy`][wybthon.lazy].
- Typed components: inputs declared on a [`Props`][wybthon.Props] class that pyright and mypy check without a plugin.
- A client-side router in `wybthon.router` with [`Router`][wybthon.router.Router], [`Route`][wybthon.router.Route], and [`Link`][wybthon.router.Link].
- [Server rendering](concepts/server-rendering.md): prerender routes at build time or render per request in CPython, stream `Loading` boundaries, set the status and headers with [`http_status`][wybthon.http_status] and [`http_header`][wybthon.http_header], and [`hydrate`][wybthon.hydrate] the result in the browser.
- Form state, validators, and accessibility helpers in `wybthon.forms`.
- A test renderer, [`wybthon.testing`](api/testing.md), that mounts components into an in-memory DOM in plain CPython.
- A dev server (`wyb dev`) with hot reload via Server-Sent Events, and production builds (`wyb build`) with dev-mode checks turned off.

## Try it in 30 seconds

The smallest interactive Wybthon component looks like this:

```python
from wybthon import button, component, create_signal, div, p, render


@component
def Counter():
    count, set_count = create_signal(0)
    return div(
        p(t"Count: {count}"),
        button("Increment", on_click=lambda: set_count(lambda n: n + 1)),
    )


render(Counter(), "#app")
```

`count` is an accessor. Interpolating it in a template string (`t"..."`, new in Python 3.14) creates a reactive hole, so only that text node updates when the signal changes. Walk through this example end to end in [Getting started](getting-started.md), or jump straight into the [Concepts](concepts/mental-model.md) section.

## Quickstart

1. Install Wybthon (Python 3.14 or newer):

    ```bash
    pip install wybthon
    ```

2. Create a project and run the dev server with auto-reload:

    ```bash
    wyb init my-app
    cd my-app
    wyb dev --open
    ```

3. Explore the [demo apps](guides/demo-app.md) and the API in the Concepts and API sections.

## Why Wybthon?

- **Run-once components and typed props.** A `@component` declares its inputs on a [`Props`][wybthon.Props] class, and each [`Prop[T]`][wybthon.Prop] field reads as an accessor. Place it in the tree to bind it, call it inside a memo or effect to derive from it, or `.peek()` it for a one-time read. Callbacks are plain fields, passed through untouched.
- **Holes are the unit of update.** A zero-argument callable or accessor anywhere in the tree becomes its own render effect. There are no component re-renders to reason about.
- **Automatic batching.** Signal writes are staged and applied once per microtask (and at the end of every event handler). There's no `batch()`; call [`flush`][wybthon.flush] only when you need the settled state synchronously.
- **Async is part of the graph.** Reading an async memo before it resolves raises [`NotReadyError`][wybthon.NotReadyError], which the nearest `Loading` boundary turns into fallback UI. Content stays mounted while pending, and a later refetch runs as a transition: the UI that depends on the change holds on the previous state until the new value lands, so nothing tears.
- **A virtual DOM where it pays off.** Python has no JSX compiler to separate static from dynamic markup, and every DOM call crosses the Pyodide bridge, so Wybthon diffs small subtrees and ships the resulting ops to a JavaScript kernel in one batch. Repeated subtrees mount through a generated function per shape and one fused clone command each.
- **Dev-mode diagnostics.** Writing a signal inside a tracking scope raises [`WriteInScopeError`][wybthon.WriteInScopeError]; reading a signal or prop at the top level of a component body warns, because that read isn't tracked; an unknown or missing prop raises `TypeError`. Production builds turn these checks off.
- **Runs anywhere Python runs.** The reactive core and the VDOM are pure Python, so component tests run in CPython with [`wybthon.testing`](api/testing.md).

## Documentation map

- **Get started**: install, write your first component, explore the dev server.
- **Concepts**: deep dives into the [mental model](concepts/mental-model.md), reactivity, components, lifecycle, VDOM, and DOM interop.
- **Guides**: task-oriented recipes for [authoring patterns](guides/authoring-patterns.md), [testing](guides/testing.md), [performance](guides/performance.md), [typing](guides/typing.md), [deployment](guides/deployment.md), and more.
- **Examples**: complete, runnable modules for a counter, async fetch, forms, error handling, and routing.
- **API reference**: auto-generated documentation per module via `mkdocstrings`.
- **Meta**: contribution guide, [documentation style guide](meta/style-guide.md), FAQ, and troubleshooting.

## Next steps

- New to Wybthon? Start with [Getting started](getting-started.md).
- Coming from React or SolidJS? Read [Mental model](concepts/mental-model.md) and the migration guides ([from React](guides/migrating-from-react.md), [from Solid](guides/migrating-from-solid.md)).
- Review [runtime contracts](concepts/runtime-contracts.md) for state visibility, ownership, and async behavior.
- Looking for an API symbol? Use the search box at the top of the page or jump to the [API reference](api/wybthon.md).
