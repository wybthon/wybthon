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
- Flow control ([`Show`][wybthon.Show], [`For`][wybthon.For], [`Repeat`][wybthon.Repeat], [`Switch`][wybthon.Switch], [`Dynamic`][wybthon.Dynamic]), callable [`Context`][wybthon.Context] objects, [`Portal`][wybthon.Portal], and [`lazy`][wybthon.lazy].
- A client-side router with [`Router`][wybthon.Router], [`Route`][wybthon.Route], and [`Link`][wybthon.Link].
- Form state, validators, and accessibility helpers.
- A dev server (`wyb dev`) with hot reload via Server-Sent Events.

## Try it in 30 seconds

The smallest interactive Wybthon component looks like this:

```python
from wybthon import button, component, create_signal, div, p, render


@component
def Counter():
    count, set_count = create_signal(0)
    return div(
        p("Count: ", count),
        button("Increment", on_click=lambda e: set_count(lambda n: n + 1)),
    )


render(Counter(), "#app")
```

`count` is an accessor. Placing it in the tree creates a reactive hole, so only that text node updates when the signal changes. Walk through this example end to end in [Getting started](getting-started.md), or jump straight into the [Concepts](concepts/mental-model.md) section.

## Quickstart

1. Install Wybthon (Python 3.12 or newer):

    ```bash
    pip install wybthon
    ```

2. Clone the [demo-template](https://github.com/wybthon/demo-template) and run the dev server with auto-reload:

    ```bash
    git clone https://github.com/wybthon/demo-template.git my-app
    cd my-app
    wyb dev --dir . --watch app --open
    ```

3. Explore the [demo apps](guides/demo-app.md) and the API in the Concepts and API sections.

## Why Wybthon?

- **Run-once components and typed props.** Every parameter of a `@component` function is a [`Prop[T]`][wybthon.Prop] accessor. Place it in the tree to bind it, call it inside a memo or effect to derive from it, or `.peek()` it for a one-time read.
- **Holes are the unit of update.** A zero-argument callable or accessor anywhere in the tree becomes its own render effect. There are no component re-renders to reason about.
- **Automatic batching.** Signal writes are staged and applied once per microtask (and at the end of every event handler). There's no `batch()`; call [`flush`][wybthon.flush] only when you need the settled state synchronously.
- **Async is part of the graph.** Reading an async memo before it resolves raises [`NotReadyError`][wybthon.NotReadyError], which the nearest `Loading` boundary turns into fallback UI. Content stays mounted while pending, and a later refetch runs as a transition: the UI that depends on the change holds on the previous state until the new value lands, so nothing tears.
- **A virtual DOM where it pays off.** Python has no JSX compiler to separate static from dynamic markup, and every DOM call crosses the Pyodide bridge, so Wybthon diffs small subtrees and ships the resulting ops to a JavaScript kernel in one batch. Static subtrees mount from cloned templates.
- **Dev-mode diagnostics.** Writing a signal inside a tracking scope raises [`WriteInScopeError`][wybthon.WriteInScopeError]; reading a signal or prop at the top level of a component body warns, because that read isn't tracked.
- **Runs anywhere Python runs.** The reactive core and the VDOM are pure Python, so unit tests run in CPython against a stub backend.

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
- Upgrading from an earlier Wybthon release? See [Migrating from 0.2x and 0.30](guides/migrating-from-0-x.md).
- Looking for an API symbol? Use the search box at the top of the page or jump to the [API reference](api/wybthon.md).
