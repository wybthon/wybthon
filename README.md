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

Wybthon brings SolidJS 2.0's reactive model to Python and runs it in the browser through [Pyodide](https://pyodide.org/). You write run-once function components with typed props and return HTML written as Python 3.14 template strings: `html(t"<p>Count: {count}</p>")`. Signals, memos, and small reactive expressions placed in that markup update only the text nodes and attributes that read them; components never re-render. Async data, loading and error boundaries, actions with optimistic state, draft-first stores, server rendering, a router, forms, and context are all built in.

## Features

- **HTML templates that compile once.** `html(t"...")` takes a [PEP 750](https://peps.python.org/pep-0750/) template string. Each literal is parsed and compiled once, and every later call clones a native `<template>` with one command and fills its slots. It's the job Solid's compiler does for JSX, done by the language with no build step.
- **Run-once components with typed props.** Components declare their inputs on a `Props` class. `Prop[T]` fields are reactive accessors; plain fields carry callbacks untouched. Pyright, Pylance, and mypy check every component call with no plugin.
- **Components cost what their markup costs.** A constant prop subscribes to nothing, a binding that reads nothing reactive is dropped after its first run, and `Show`, `For`, `Repeat`, and `Switch` are native regions rather than wrapper components.
- **Signals with automatic batching.** `create_signal`, `create_memo`, and `create_effect`. Writes are staged and applied once per microtask (and at the end of every event handler), so there's no `batch()` to remember.
- **Async-first data.** An `async def` passed to `create_memo` is the data-fetching primitive. `Loading` shows a fallback until it resolves; later refetches run as **transitions** that hold the dependent UI on the old state until the new value lands, so the screen never tears. `is_pending`, `latest`, `resolve`, and `refresh` observe or drive it.
- **Actions and optimistic state.** `action` makes a mutation a transaction; `create_optimistic` and `create_optimistic_store` show temporary values that revert when the action settles.
- **Draft-first stores.** `create_store` setters take a function that mutates a draft with plain Python; reads are tracked per path. `reconcile`, `snapshot`, `deep`, and projections are included.
- **Flow control and boundaries.** `Show`, `For`, `Repeat`, `Switch`/`Match`, and `dynamic` update only the affected subtree; `Loading`, `Reveal`, and `Errored` swap in fallbacks without tearing down sibling trees.
- **Server rendering and hydration.** Render the same components to HTML in CPython at build time or per request, stream `Loading` boundaries as they resolve, set the response status and headers from components, and `hydrate` the result in the browser.
- **One bridge crossing per update.** A small virtual DOM batches every mutation in a flush into one call to a JavaScript kernel, which matters when every DOM call would otherwise cross from Python to JavaScript.
- **Router, forms, context, portals, and lazy components.** `wybthon.router`, `wybthon.forms` with validators and ARIA helpers, callable `Context` objects, `Portal`, and `lazy` with explicit build chunks.
- **Testing in plain CPython.** `wybthon.testing` renders components into an in-memory DOM and queries them by text, role, label, and test id.
- **Tooling.** `wyb init` scaffolds a project, `wyb dev` rebuilds and reloads on change, and `wyb build` writes a production bundle with the manifest inlined and the runtime preloaded.

## Quick start

### Installation

Wybthon requires Python 3.14.

```bash
pip install wybthon
wyb init my-app
cd my-app
wyb dev --open
```

### Usage

```python
from collections.abc import Callable

from wybthon import (
    Errored,
    For,
    Loading,
    ParentProps,
    Prop,
    Props,
    Show,
    action,
    component,
    create_memo,
    create_signal,
    create_store,
    html,
    prop,
    render,
)


class CounterProps(Props):
    step: Prop[int] = prop(default=1)
    on_change: Callable[[int], None] | None = None


@component
def Counter(props: CounterProps):
    count, set_count = create_signal(0)
    doubled = create_memo(lambda: count() * 2)
    many = create_memo(lambda: count() > 5)

    def increment():
        set_count(lambda n: n + props.step())
        if props.on_change is not None:
            props.on_change(count.peek() + props.step.peek())

    return html(t"""
      <div>
        <p>Count: {count} (doubled: {doubled})</p>
        <button onclick={increment}>+</button>
        {Show(many, html(t"<p>That's a lot of clicks.</p>"))}
      </div>
    """)


class PanelProps(ParentProps):
    title: Prop[str]


@component
def Panel(props: PanelProps):
    return html(t'<section class="panel"><h2>{props.title}</h2>{props.children}</section>')


@component
def Todos():
    store, set_store = create_store({"todos": []})
    draft, set_draft = create_signal("")

    @action
    async def add(title: str):
        set_store(lambda s: s.todos.append({"id": len(s.todos) + 1, "title": title}))
        set_draft("")

    def todo(item, index):
        return html(t"<li>{(lambda: item().title)}</li>")

    return html(t"""
      <div>
        <input value={draft} oninput={(lambda e: set_draft(e.target.value))}>
        <button onclick={(lambda: add(draft.peek()))} disabled={add.pending}>Add</button>
        <ul>{For(store.todos, todo, keyed=lambda t: t["id"])}</ul>
      </div>
    """)


def failed(err, reset):
    return html(t"<div><p>Something went wrong: {(lambda: str(err()))}</p><button onclick={reset}>Retry</button></div>")


@component
def App():
    return Errored(
        Loading(
            html(t"""
              <main>
                <{Panel} title="Counter"><{Counter} step={2} on_change={print} /></{Panel}>
                <{Panel} title="Todos"><{Todos} /></{Panel}>
              </main>
            """),
            fallback=html(t"<p>Loading...</p>"),
        ),
        fallback=failed,
    )


render(App(), "#app")
```

Python doesn't allow a bare `lambda` inside a t-string interpolation, so inline handlers are wrapped in parentheses, as in `{(lambda: ...)}`, or given a name. Named handlers and memos usually read better anyway. The element helpers (`div(...)`, `p(...)`) remain available when markup is built by code; see [Templates](https://wybthon.com/concepts/templates/).

In a project created with `wyb init`, return the root view from the entry function in `app/main.py` instead of calling `render`; the generated bootstrap renders it, or hydrates it when the page was prerendered. List routes under `prerender` in `wybthon.toml` to render them to HTML at build time. See [Server rendering](https://wybthon.com/concepts/server-rendering/).

Components are testable in plain CPython:

```python
from wybthon.testing import fire, render


def test_counter():
    with render(Counter(step=2)) as screen:
        fire.click(screen.get_by_role("button", name="+"))
        assert screen.get_by_text("Count: 2 (doubled: 4)")
```

## Documentation

Visit [wybthon.com](https://wybthon.com/) for the full documentation, including getting started guides, core concepts, API reference, working examples, and migration guides from React and Solid. Large changes are designed in [RFCs](docs/rfcs/index.md).

## Contributing

Contributions are welcome. Please see [CONTRIBUTING.md](CONTRIBUTING.md) for setup instructions, coding standards, and guidelines for submitting pull requests.

## License

[MIT](LICENSE)
