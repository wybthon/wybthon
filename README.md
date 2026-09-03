<p align="center">
  <img src="docs/assets/banner.jpg" alt="Wybthon" width="800" />
</p>

<p align="center">
  <em>SolidJS for Python. Build interactive web apps in Python, no JavaScript required.</em>
</p>

<p align="center">
  <a href="https://github.com/wybthon/wybthon/actions/workflows/ci.yml"><img src="https://github.com/wybthon/wybthon/actions/workflows/ci.yml/badge.svg" alt="CI" /></a>
  <a href="https://github.com/wybthon/wybthon/actions/workflows/release.yml"><img src="https://github.com/wybthon/wybthon/actions/workflows/release.yml/badge.svg" alt="Release" /></a>
  <a href="https://pypi.org/project/wybthon/"><img src="https://img.shields.io/pypi/v/wybthon" alt="PyPI Version" /></a>
  <a href="https://pypi.org/project/wybthon/"><img src="https://img.shields.io/pypi/pyversions/wybthon" alt="Python Versions" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/pypi/l/wybthon" alt="License: MIT" /></a>
  <a href="https://wybthon.com/"><img src="https://img.shields.io/website?url=https%3A%2F%2Fwybthon.com&label=docs" alt="Docs" /></a>
</p>

<p align="center">
  <a href="https://wybthon.com/">Documentation</a> ·
  <a href="https://wybthon.com/getting-started/">Getting Started</a> ·
  <a href="https://wybthon.com/examples/">Examples</a> ·
  <a href="CONTRIBUTING.md">Contributing</a>
</p>

---

## Overview

Wybthon brings SolidJS 2.0's reactive model to Python and runs it in the browser through [Pyodide](https://pyodide.org/). You write run-once function components, return a tree of HTML helpers, and drop signals, memos, and small reactive expressions ("holes") into that tree. When a signal changes, only the holes that read it re-run; components never re-render. Async data, loading and error boundaries, actions with optimistic state, draft-first stores, a router, forms, and context are all built in.

## Features

- **Run-once components with typed props.** `@component` functions run once at mount. Every parameter is a `Prop[T]` accessor: call it for a tracked read, `.peek()` for a one-time read, or place it in the tree to bind it.
- **Reactive holes, not re-renders.** Any zero-argument callable or accessor placed in the tree becomes its own render effect. A signal write re-runs only the holes that depend on it.
- **Signals with automatic batching.** `create_signal`, `create_memo`, and `create_effect`. Writes are staged and applied once per microtask (and at the end of every event handler), so there is no `batch()` to remember.
- **Async-first data.** An `async def` passed to `create_memo` is the data-fetching primitive. `Loading` shows a fallback until it resolves, later refetches serve the stale value while revalidating, and `is_pending`, `latest`, `resolve`, and `refresh` observe or drive it.
- **Actions and optimistic state.** `action` tracks in-flight mutations; `create_optimistic` and `create_optimistic_store` hold temporary values that revert when the actions settle.
- **Draft-first stores.** `create_store` setters take a function that mutates a draft with plain Python; reads are tracked per path. `reconcile`, `snapshot`, `deep`, derived stores, and projections are included.
- **Flow control.** `Show`, `For`, `Repeat`, `Switch`/`Match`, and `Dynamic` create isolated reactive scopes so only the affected subtree updates.
- **Boundaries.** `Loading`, `Reveal`, and `Errored` keep content mounted while pending and swap in fallbacks without tearing down sibling trees.
- **Virtual DOM behind the scenes.** Every DOM mutation is batched through a small JS kernel in a single Python-to-JS crossing, and static subtrees mount from cloned templates.
- **Router, forms, context, portals, lazy components.** `Router`, `Route`, `Link`, `form_state` with validators and ARIA helpers, callable `Context` objects, `Portal`, and `lazy`.
- **Dev mode diagnostics.** Writes inside a tracking scope raise `WriteInScopeError`; untracked reads at the top of a component body warn.
- **Dev server with hot reload.** `wyb dev` serves your project and reloads the page over Server-Sent Events.

## Quick start

### Installation

Wybthon requires Python 3.12 or newer.

```bash
pip install wybthon
```

Inside Pyodide, install at runtime with `micropip`:

```python
import micropip
await micropip.install("wybthon")
```

### Usage

```python
from wybthon import (
    Errored,
    For,
    Loading,
    Prop,
    Show,
    action,
    button,
    component,
    create_memo,
    create_signal,
    create_store,
    div,
    input_,
    li,
    p,
    prop,
    render,
    ul,
)


@component
def Counter(step: Prop[int] = prop(1)):
    count, set_count = create_signal(0)
    doubled = create_memo(lambda: count() * 2)
    return div(
        p("Count: ", count, " (doubled: ", doubled, ")"),
        button("+", on_click=lambda e: set_count(lambda n: n + step())),
        Show(lambda: count() > 5, lambda: p("That's a lot of clicks.")),
    )


@component
def Todos():
    store, set_store = create_store({"items": []})
    draft, set_draft = create_signal("")

    @action
    async def add(title: str):
        set_store(lambda s: s.items.append({"id": len(s.items) + 1, "title": title}))
        set_draft("")

    return div(
        input_(value=draft, on_input=lambda e: set_draft(e.target.value)),
        button("Add", on_click=lambda e: add(draft.peek()), disabled=add.pending),
        ul(For(lambda: store.items, lambda item, i: li(lambda: item()["title"]), keyed=lambda t: t["id"])),
    )


@component
def App():
    return Errored(
        lambda: Loading(lambda: div(Counter(step=2), Todos()), fallback=p("Loading...")),
        fallback=lambda err, reset: div(p("Something went wrong: ", str(err)), button("Retry", on_click=lambda e: reset())),
    )


render(App(), "#app")
```

## Documentation

Visit [wybthon.com](https://wybthon.com/) for the full documentation, including getting started guides, core concepts, API reference, working examples, and migration guides from React, Solid, and earlier Wybthon releases.

## Contributing

Contributions are welcome. Please see [CONTRIBUTING.md](CONTRIBUTING.md) for setup instructions, coding standards, and guidelines for submitting pull requests.

## License

[MIT](LICENSE)
