<p align="center">
  <img src="docs/assets/banner.jpg" alt="Wybthon" width="800" />
</p>

<p align="center">
  <em>Build interactive web apps in Python, no JavaScript required.</em>
</p>

<p align="center">
  <a href="https://github.com/wybthon/wybthon/actions/workflows/ci.yml"><img src="https://github.com/wybthon/wybthon/actions/workflows/ci.yml/badge.svg" alt="CI" /></a>
  <a href="https://github.com/wybthon/wybthon/actions/workflows/release.yml"><img src="https://github.com/wybthon/wybthon/actions/workflows/release.yml/badge.svg" alt="Release" /></a>
  <a href="https://pypi.org/project/wybthon/"><img src="https://img.shields.io/pypi/v/wybthon" alt="PyPI Version" /></a>
  <a href="https://pypi.org/project/wybthon/"><img src="https://img.shields.io/pypi/pyversions/wybthon" alt="Python Versions" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/pypi/l/wybthon" alt="License: MIT" /></a>
  <a href="https://docs.wybthon.com/"><img src="https://img.shields.io/website?url=https%3A%2F%2Fdocs.wybthon.com&label=docs" alt="Docs" /></a>
</p>

<p align="center">
  <a href="https://docs.wybthon.com/">Documentation</a> ·
  <a href="https://docs.wybthon.com/getting-started/">Getting Started</a> ·
  <a href="https://docs.wybthon.com/examples/">Examples</a> ·
  <a href="CONTRIBUTING.md">Contributing</a>
</p>

---

## Overview

Wybthon is a client-side SPA framework that lets you build interactive web applications entirely in Python. Powered by Pyodide, it runs in the browser and provides a signals-first reactive model inspired by SolidJS. With fine-grained reactivity, a virtual DOM, component model, routing, forms, and context, you can write modern frontends without touching JavaScript.

## Features

- **Run-once components + reactive holes:** function bodies run a single
  time at mount.  Embed a signal getter anywhere in your VNode tree and
  the reconciler wires it as a *reactive hole* — only that DOM node
  updates when the signal changes.  No React-style re-renders.
- **Signals-first reactivity:** Fine-grained updates with `create_signal`,
  `create_effect`, `create_memo`, `batch`, `untrack`, and `on`.
- **Virtual DOM:** Function components with efficient, batched diffing —
  amortising the Pyodide ↔ JS bridge cost while keeping SolidJS-style
  fine-grained updates above it.
- **Client-side router:** Path parameters, query parsing, `Link`
  component, and programmatic navigation.
- **Context API:** Share state across the component tree with
  `create_context` and `use_context`.
- **Forms and validation:** Built-in form state management with
  validators and two-way bindings.
- **Flow control primitives:** `Show`, `For`, `Index`, `Switch`,
  `Match`, and `Dynamic` for declarative rendering.
- **Error boundaries and Suspense:** Graceful error handling and async
  loading states.
- **Dev server with hot reload:** `wyb dev` launches a local server
  with SSE-based auto-reload.

## Quick Start

### Installation

```bash
pip install wybthon
```

### Usage

```python
from wybthon import button, component, create_signal, div, p, span


@component
def Counter(initial: int = 0):
    count, set_count = create_signal(initial)
    # The body runs ONCE.  ``count.get`` is a reactive hole — only the
    # text node inside the span updates when the signal changes.
    return div(
        p("Count: ", span(count.get)),
        button("Increment", on_click=lambda e: set_count(count() + 1)),
    )
```

## Documentation

Visit [docs.wybthon.com](https://docs.wybthon.com/) for the full documentation, including getting started guides, core concepts, API reference, and working examples.

## Contributing

Contributions are welcome. Please see [CONTRIBUTING.md](CONTRIBUTING.md) for setup instructions, coding standards, and guidelines for submitting pull requests.

## License

[MIT](LICENSE)
