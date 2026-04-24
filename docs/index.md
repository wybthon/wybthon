# Wybthon

Wybthon is a client-side Python single-page application (SPA) framework that runs in the browser via [Pyodide](https://pyodide.org/).

If you can write Python, you can build interactive web apps with Wybthon — no JavaScript build pipeline required.

## What is Wybthon?

Wybthon brings a SolidJS-style fine-grained reactive model to Python. You write function components in Python, return a virtual DOM tree, and the framework patches the real DOM in response to signal updates. Components run **once**; only the values that actually change re-render.

The framework ships with everything you need to build a real app:

- A virtual DOM renderer with batched DOM mutations.
- Reactive primitives ([`create_signal`][wybthon.create_signal], [`create_effect`][wybthon.create_effect], [`create_memo`][wybthon.create_memo], [`create_resource`][wybthon.create_resource]).
- Reactive [`Provider`][wybthon.Provider] / [`use_context`][wybthon.use_context] for context propagation without forced re-renders.
- A small client-side router with [`Route`][wybthon.Route] and [`Link`][wybthon.Link].
- Form state, validators, and accessibility helpers.
- A dev server (`wyb dev`) with hot reload via Server-Sent Events.

## Try it in 30 seconds

The smallest interactive Wybthon component looks like this:

```python
from wybthon import component, create_signal, dynamic
from wybthon.html import button, div, p


@component
def Counter():
    count, set_count = create_signal(0)

    return div(
        p("Count: ", dynamic(lambda: count())),
        button("Increment", on_click=lambda _e: set_count(count() + 1)),
    )
```

Walk through this example end-to-end in [Getting started](getting-started.md), or jump straight into the [Concepts](concepts/primitives.md) section.

## Quickstart

1) Run the demo straight from a checkout:

    ```bash
    python -m http.server
    # open http://localhost:8000/examples/demo/index.html
    ```

2) Or run the dev server with auto-reload:

    ```bash
    pip install .
    wyb dev --dir .
    ```

3) Explore the demo app in `examples/demo` and the API in the Concepts and API sections.

## Why Wybthon?

- **Fully reactive props + run-once components**: function components run a single time at mount. Every prop is a zero-argument accessor — pass it into the tree for an automatic *reactive hole* and only that node updates when the prop changes. No React-style re-renders. See [Reactive Holes](concepts/primitives.md#reactive-holes).
- **Signals-first** reactive model: `create_signal`, `create_effect`, `create_memo`, `on_mount`, `on_cleanup`, `batch`, `untrack`, `on`, `dynamic`.
- Virtual DOM renderer with function components — **batched** mutations amortise the Pyodide ↔ JS bridge cost.
- Async data: [`create_resource`][wybthon.create_resource] with loading/error signals and a [`Suspense`][wybthon.Suspense] boundary.
- **Reactive context**: `Provider` values are signal-backed so consumers update without re-mounting the subtree.
- Router with path params, query parsing, and a `Link` component.
- DOM helpers and delegated event handling.
- Forms state, validators, and accessibility-friendly bindings.
- Dev server with hot reload via Server-Sent Events.
- **Dev-mode warnings** for the most common reactive footguns (destructured prop access, plain-list `each=`, legacy render returns).

## Documentation map

- **Get started** — install, run the demo, write your first component, explore the dev server.
- **Concepts** — deep dives into the [mental model](concepts/mental-model.md), reactivity, components, lifecycle, VDOM, and DOM interop.
- **Guides** — task-oriented recipes for [forms](concepts/forms.md), [routing](concepts/router.md), [stores](concepts/stores.md), [suspense and lazy loading](concepts/suspense-lazy.md), [testing](guides/testing.md), and more.
- **Examples** — walkthroughs of the demo app pages and patterns.
- **API reference** — auto-generated documentation per module via `mkdocstrings`.
- **Meta** — contribution guide, [documentation style guide](meta/style-guide.md), FAQ, and troubleshooting.

## Next steps

- New to Wybthon? Start with [Getting started](getting-started.md).
- Coming from React or SolidJS? Read [Mental model](concepts/mental-model.md) and the migration guides ([from React](guides/migrating-from-react.md), [from Solid](guides/migrating-from-solid.md)).
- Looking for an API symbol? Use the search box (top of the page) or jump to the [API reference](api/wybthon.md).
