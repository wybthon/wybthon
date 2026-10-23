# Wybthon

Wybthon is SolidJS for Python: a client-side single-page application (SPA) framework with SolidJS 2.0's fine-grained reactive model, a Pythonic API, and a runtime that lives in the browser through [Pyodide](https://pyodide.org/).

If you can write Python, you can build interactive web apps with Wybthon. There's no JavaScript build pipeline and no JSX: markup is HTML in a Python template string.

## What is Wybthon?

You write function components in Python and return HTML written as Python 3.14 template strings: `html(t"<p>Count: {count()}</p>")`. Like Solid's, Wybthon's compiler turns every dynamic expression in that markup into a getter, and each template literal into a native `<template>` that the browser clones per instance, so the expressions you interpolate are its only moving parts. Components run **once**. When a signal changes, only the text nodes, attributes, and reactive holes that read it update, and the renderer batches the resulting DOM mutations into a single crossing of the Python-to-JavaScript bridge.

The framework ships with everything you need to build a real app:

- [Templates](concepts/templates.md): [`html`][wybthon.html] takes a t-string of ordinary HTML, with interpolations for text, attributes, events, refs, spreads, and component tags. [`h`][wybthon.h] is the programmatic layer.
- [The compiler](concepts/compiler.md): `{count() * 2}` and `{props.title}` stay reactive without being wrapped, and production builds never parse a template at run time.
- Reactive primitives: [`create_signal`][wybthon.create_signal], [`create_memo`][wybthon.create_memo], and [`create_effect`][wybthon.create_effect], with automatic batching and typed accessors.
- Async-first data: an `async def` passed to `create_memo` is the fetching primitive, and [`create_deferred`][wybthon.create_deferred] is the async memo that never holds the rest of the UI; [`Loading`][wybthon.Loading] and [`Errored`][wybthon.Errored] boundaries handle the pending and failure states.
- [`action`][wybthon.action] with [`create_optimistic`][wybthon.create_optimistic] and [`create_optimistic_store`][wybthon.create_optimistic_store] for mutations.
- Draft-first stores ([`create_store`][wybthon.create_store], [`reconcile`][wybthon.reconcile], [`create_projection`][wybthon.create_projection]).
- Flow control ([`Show`][wybthon.Show], [`For`][wybthon.For], [`Repeat`][wybthon.Repeat], [`Switch`][wybthon.Switch], [`dynamic`][wybthon.dynamic]), callable [`Context`][wybthon.Context] objects, [`Portal`][wybthon.Portal], [`lazy`][wybthon.lazy], and [`lazy_module`][wybthon.lazy_module].
- Typed components: inputs declared as plain annotations on a [`Props`][wybthon.Props] class that pyright and mypy check without a plugin.
- A client-side router in `wybthon.router` with [`Router`][wybthon.router.Router], [`Route`][wybthon.router.Route], and [`Link`][wybthon.router.Link].
- [Server rendering](concepts/server-rendering.md): prerender routes at build time or render per request in CPython, stream `Loading` boundaries, set the status and headers with [`http_status`][wybthon.http_status] and [`http_header`][wybthon.http_header], and [`hydrate`][wybthon.hydrate] the result in the browser.
- Form state, validators, and accessibility helpers in `wybthon.forms`.
- A test renderer, [`wybthon.testing`](api/testing.md), that mounts components into an in-memory DOM in plain CPython, and a pytest plugin that compiles templates in test modules.
- A dev server (`wyb dev`) with hot reload via Server-Sent Events, production builds (`wyb build`) with templates compiled ahead of time, dev-mode checks turned off, the asset manifest inlined, and the runtime preloaded, and `wyb run` for scripts.

## Try it in 30 seconds

The smallest interactive Wybthon component looks like this:

```python
from wybthon import component, create_signal, html, render


@component
def Counter():
    count, set_count = create_signal(0)

    def increment():
        set_count(lambda n: n + 1)

    return html(t"""
      <div>
        <p>Count: {count()}</p>
        <button onclick={increment}>Increment</button>
      </div>
    """)


render(Counter(), "#app")
```

`t"..."` is a [PEP 750](https://peps.python.org/pep-0750/) template string, new in Python 3.14. `{count()}` calls something, so the compiler turns it into a getter: a reactive binding, and only that text node updates when the signal changes. Walk through this example end to end in [Getting started](getting-started.md), read the [Templates](concepts/templates.md) guide, or jump straight into the [Concepts](concepts/mental-model.md) section.

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

- **Run-once components and typed props.** A `@component` declares its inputs on a [`Props`][wybthon.Props] class with plain annotations, and `props.title` is a tracked read of the parent's value, as in Solid. Use it in the markup to bind it, in a memo or effect to derive from it, or in [`untrack`][wybthon.untrack] for a one-time read. Callbacks are fields annotated as callable, passed through untouched.
- **A compiler, as in Solid.** The [compiler](concepts/compiler.md) rewrites each template before its module runs: an expression that calls something, reads an attribute, or indexes becomes a getter, and a component call in the markup receives getters for its props. You write `{count() * 2}`, not a lambda.
- **Markup compiles ahead of time.** Each template literal is parsed, validated, and turned into a mount function when its module is compiled; every instance clones its native `<template>` with one kernel command and fills its slots. Production builds never parse a template or generate code at run time.
- **Holes are the unit of update.** Each dynamic expression in the markup becomes its own binding. There are no component re-renders to reason about.
- **Components cost what their markup costs.** A constant prop subscribes to nothing, a binding that reads nothing reactive allocates no computation, and `Show`, `For`, `Repeat`, and `Switch` are native regions rather than wrapper components.
- **Automatic batching.** Signal writes are staged and applied once per microtask (and at the end of every event handler). There's no `batch()`; call [`flush`][wybthon.flush] only when you need the settled state synchronously.
- **Async is part of the graph.** Reading an async memo before it resolves raises [`NotReadyError`][wybthon.NotReadyError], which the nearest `Loading` boundary turns into fallback UI. Content stays mounted while pending, and a later refetch runs as a transition: the UI that depends on the change holds on the previous state until the new value lands, so nothing tears.
- **A virtual DOM where it pays off.** Every DOM call crosses the Pyodide bridge, so Wybthon emits DOM operations into a buffer and ships them to a JavaScript kernel in one batch per flush. Only reactive holes that return new markup are diffed, and a template from the same literal is patched slot by slot.
- **Dev-mode diagnostics.** Writing a signal inside a tracking scope raises [`WriteInScopeError`][wybthon.WriteInScopeError]; reading a signal or prop at the top level of a component body warns, because that read isn't tracked; an unknown or missing prop raises `TypeError`; a template that reached `html()` without the compiler raises [`TemplateError`][wybthon.TemplateError]. Production builds turn these checks off.
- **Runs anywhere Python runs.** The reactive core and the VDOM are pure Python, so component tests run in CPython with [`wybthon.testing`](api/testing.md).

## Documentation map

- **Get started**: install, write your first component, explore the dev server.
- **Concepts**: deep dives into the [mental model](concepts/mental-model.md), [templates](concepts/templates.md), [the compiler](concepts/compiler.md), reactivity, components, lifecycle, VDOM, and DOM interop.
- **Guides**: task-oriented recipes for [authoring patterns](guides/authoring-patterns.md), [testing](guides/testing.md), [performance](guides/performance.md), [typing](guides/typing.md), [deployment](guides/deployment.md), and more.
- **Examples**: complete, runnable modules for a counter, async fetch, forms, error handling, and routing.
- **API reference**: auto-generated documentation per module via `mkdocstrings`.
- **Meta**: contribution guide, [documentation style guide](meta/style-guide.md), FAQ, and troubleshooting.

## Next steps

- New to Wybthon? Start with [Getting started](getting-started.md).
- Coming from React or SolidJS? Read [Mental model](concepts/mental-model.md) and the migration guides ([from React](guides/migrating-from-react.md), [from Solid](guides/migrating-from-solid.md)).
- Review [runtime contracts](concepts/runtime-contracts.md) for state visibility, ownership, and async behavior.
- Looking for an API symbol? Use the search box at the top of the page or jump to the [API reference](api/wybthon.md).
