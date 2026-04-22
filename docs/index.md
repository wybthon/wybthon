# Wybthon

Wybthon is a client-side Python SPA framework that runs in the browser via Pyodide.

## What is Wybthon?

Build interactive web apps in Python that execute entirely in the browser. Wybthon provides a Virtual DOM renderer, reactive primitives, routing, forms, and DOM/event interop, all designed for Pyodide.

## Features

- **Run-once components + reactive holes**: function components run a single
  time at mount.  Embed signal getters anywhere in your VNode tree to create
  a *reactive hole* — only that node updates when the signal changes.  No
  React-style component re-renders.  See [Reactive Holes](concepts/primitives.md#reactive-holes).
- **Signals-first** reactive model: `create_signal`, `create_effect`, `create_memo`, `on_mount`, `on_cleanup`, `batch`, `untrack`, `on`
- Virtual DOM renderer with function components — **batched** mutations
  amortise the Pyodide ↔ JS bridge cost
- Async data: `create_resource` with loading/error signals and `Suspense`
- Router with path params, query parsing, and a `Link` component
- Contexts and a `Provider` component
- DOM helpers and event delegation
- Forms state, validators, and bindings
- Dev server with hot-reload (SSE)

## Quickstart

1) Clone the repo and run the demo:

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

## Documentation map

- Getting Started: install, run the demo, dev server
- Concepts: deep dives into VDOM, components, reactivity, router, context, events, forms, DOM, error boundaries
- Guides: dev server, demo app, Pyodide integration, deployment, testing, performance, typing
- Examples: walkthroughs for the demo’s pages and patterns
- API Reference: auto-generated docs per module via mkdocstrings

> TODO: Add a small end-to-end example on the homepage once the component authoring guide is finalized.
> TODO: Add a screenshot of the demo app landing page.
