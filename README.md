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

Wybthon brings SolidJS 2.0's reactive model to Python and runs it in the browser through [Pyodide](https://pyodide.org/). You write run-once function components with typed props and return HTML written as Python 3.14 template strings: `html(t"<p>Count: {count()}</p>")`. Like Solid's, Wybthon's compiler turns every dynamic expression in that markup into a getter, so each one updates only the text node or attribute that reads it; components never re-render. Async data, loading and error boundaries, actions with optimistic state, draft-first stores, server rendering, a router, forms, and context are all built in.

## Features

- **A compiler, as in Solid.** Wybthon's compiler rewrites `html(t"...")` calls on Python's syntax tree before a module runs. An expression that calls something, reads an attribute, or indexes (`{count() * 2}`, `{props.title}`, `{row["label"]}`) becomes a getter, and a component call in the markup receives getters for its props, so you never wrap markup in lambdas. It runs in `wyb build` and `wyb dev`, in an import hook that `import wybthon` installs, under pytest, and for scripts with `wyb run`.
- **HTML templates compiled ahead of time.** `html(t"...")` takes a [PEP 750](https://peps.python.org/pep-0750/) template string. The compiler parses and validates each literal and writes its mount code into the module, so a production build never parses a template or generates code at run time; every instance clones a native `<template>` with one command and fills its slots.
- **Run-once components with typed props.** Components declare their inputs on a `Props` class with plain annotations, and `props.title` is a tracked read of the parent's value, as in Solid. Callbacks are fields annotated as callable. Pyright, Pylance, and mypy check every component call with no plugin.
- **Components cost what their markup costs.** A constant prop subscribes to nothing, a binding that reads nothing reactive allocates no computation, and `Show`, `For`, `Repeat`, and `Switch` are native regions rather than wrapper components.
- **Signals with automatic batching.** `create_signal`, `create_memo`, and `create_effect`. Writes are staged and applied once per microtask (and at the end of every event handler), so there's no `batch()` to remember.
- **Async-first data.** An `async def` passed to `create_memo` is the data-fetching primitive. `Loading` shows a fallback until it resolves; later refetches run as **transitions** that hold the dependent UI on the old state until the new value lands, so the screen never tears. `create_deferred` is the async memo that never holds the rest of the UI, and `is_pending`, `latest`, `resolve`, and `refresh` observe or drive async state.
- **Actions and optimistic state.** `action` makes a mutation a transaction; `create_optimistic` and `create_optimistic_store` show temporary values that revert when the action settles.
- **Draft-first stores.** `create_store` setters take a function that mutates a draft with plain Python; reads are tracked per path. `reconcile`, `snapshot`, `deep`, and projections are included.
- **Flow control and boundaries.** `Show`, `For`, `Repeat`, `Switch`/`Match`, and `dynamic` update only the affected subtree; `Loading`, `Reveal`, and `Errored` swap in fallbacks without tearing down sibling trees.
- **Server rendering and hydration.** Render the same components to HTML in CPython at build time or per request, stream `Loading` boundaries as they resolve, set the response status and headers from components, and `hydrate` the result in the browser.
- **One bridge crossing per update.** A small virtual DOM batches every mutation in a flush into one call to a JavaScript kernel, which matters when every DOM call would otherwise cross from Python to JavaScript.
- **Memory comes back at unmount.** Removing rows or components frees them at once by reference counting, with nothing left for Python's cycle collector, and the collector's own work waits until the browser is idle.
- **Router, forms, context, portals, and lazy loading.** `wybthon.router`, `wybthon.forms` with validators and ARIA helpers, callable `Context` objects, `Portal`, and `lazy` and `lazy_module` with explicit build chunks.
- **Testing in plain CPython.** `wybthon.testing` renders components into an in-memory DOM and queries them by text, role, label, and test id. Templates in test modules are compiled by Wybthon's pytest plugin.
- **Tooling.** `wyb init` scaffolds a project, `wyb dev` rebuilds and reloads on change, `wyb build` writes a production bundle with the manifest inlined and the runtime preloaded, and `wyb run` runs a script with its templates compiled.

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
    Props,
    Show,
    action,
    component,
    create_signal,
    create_store,
    html,
    render,
)


class CounterProps(Props):
    step: int = 1
    on_change: Callable[[int], None] | None = None


@component
def Counter(props: CounterProps):
    count, set_count = create_signal(0)

    def increment():
        new_count = count() + props.step
        set_count(new_count)
        if props.on_change is not None:
            props.on_change(new_count)

    return html(t"""
      <div>
        <p>Count: {count()} (doubled: {count() * 2})</p>
        <button onclick={increment}>+</button>
        {Show(count() > 5, html(t"<p>That's a lot of clicks.</p>"))}
      </div>
    """)


class PanelProps(ParentProps):
    title: str


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

    def edit(event):
        set_draft(event.target.value)

    def submit():
        add(draft())

    def todo_row(item, index):
        return html(t"<li>{item().title}</li>")

    return html(t"""
      <div>
        <input value={draft()} oninput={edit}>
        <button onclick={submit} disabled={add.pending()}>Add</button>
        <ul>{For(store.todos, todo_row, keyed=lambda t: t["id"])}</ul>
      </div>
    """)


def failed(err, reset):
    return html(t"<div><p>Something went wrong: {str(err())}</p><button onclick={reset}>Retry</button></div>")


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

Each expression that calls something or reads an attribute, such as `{count() * 2}`, `{props.title}`, or `disabled={add.pending()}`, is compiled into a getter, so it updates on its own when what it reads changes. A call in the markup such as `{Show(count() > 5, ...)}` builds the component with a getter for each dynamic argument, the way Solid passes JSX props. Event handlers are never wrapped, and named handlers read better than inline lambdas; Python needs parentheses around an inline one (`onclick={(lambda: set_open(False))}`). Use `h(tag, props, *children)` when markup is built by code; see [Templates](https://wybthon.com/concepts/templates/) and [The compiler](https://wybthon.com/concepts/compiler/).

In a project created with `wyb init`, return the root view from the entry function in `app/main.py` instead of calling `render`; the generated bootstrap renders it, or hydrates it when the page was prerendered. List routes under `prerender` in `wybthon.toml` to render them to HTML at build time. See [Server rendering](https://wybthon.com/concepts/server-rendering/).

Components are testable in plain CPython, and Wybthon's pytest plugin compiles the templates in test modules:

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
