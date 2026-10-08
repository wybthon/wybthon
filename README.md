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

Wybthon brings SolidJS 2.0's reactive model to Python and runs it in the browser through [Pyodide](https://pyodide.org/). You write run-once function components with typed props, return a tree of HTML helpers, and drop signals, memos, t-strings, and small reactive expressions ("holes") into that tree. When a signal changes, only the holes that read it re-run; components never re-render. Async data, loading and error boundaries, actions with optimistic state, draft-first stores, server rendering, a router, forms, and context are all built in.

## Features

- **Run-once components with typed props.** Components declare their inputs on a `Props` class. `Prop[T]` fields are reactive accessors; plain fields carry callbacks untouched. Pyright, Pylance, and mypy check every component call with no plugin.
- **Reactive holes, not re-renders.** Any accessor, zero-argument callable, or t-string placed in the tree becomes its own render binding: `p(t"Count: {count}")`. A signal write re-runs only the holes that depend on it.
- **Signals with automatic batching.** `create_signal`, `create_memo`, and `create_effect`. Writes are staged and applied once per microtask (and at the end of every event handler), so there's no `batch()` to remember.
- **Async-first data.** An `async def` passed to `create_memo` is the data-fetching primitive. `Loading` shows a fallback until it resolves; later refetches run as **transitions** that hold the dependent UI on the old state until the new value lands, so the screen never tears. `is_pending`, `latest`, `resolve`, and `refresh` observe or drive it.
- **Actions and optimistic state.** `action` makes a mutation a transaction; `create_optimistic` and `create_optimistic_store` show temporary values that revert when the action settles.
- **Draft-first stores.** `create_store` setters take a function that mutates a draft with plain Python; reads are tracked per path. `reconcile`, `snapshot`, `deep`, and projections are included.
- **Flow control and boundaries.** `Show`, `For`, `Repeat`, `Switch`/`Match`, and `dynamic` update only the affected subtree; `Loading`, `Reveal`, and `Errored` swap in fallbacks without tearing down sibling trees.
- **Server rendering and hydration.** Render the same components to HTML in CPython at build time or per request, stream `Loading` boundaries as they resolve, set the response status and headers from components, and `hydrate` the result in the browser.
- **A fast virtual DOM.** Repeated subtree shapes compile into mount functions that clone a pre-parsed template in one kernel command, and every mutation in a flush crosses the Python-to-JavaScript bridge once.
- **Router, forms, context, portals, and lazy components.** `wybthon.router`, `wybthon.forms` with validators and ARIA helpers, callable `Context` objects, `Portal`, and `lazy` with explicit build chunks.
- **Testing in plain CPython.** `wybthon.testing` renders components into an in-memory DOM and queries them by text, role, label, and test id.
- **Tooling.** `wyb init` scaffolds a project, `wyb dev` rebuilds and reloads on change, and `wyb build` writes a production bundle with dev mode off.

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
    button,
    component,
    create_memo,
    create_signal,
    create_store,
    div,
    h2,
    input_,
    li,
    p,
    prop,
    render,
    section,
    ul,
)


class CounterProps(Props):
    step: Prop[int] = prop(default=1)
    on_change: Callable[[int], None] | None = None


@component
def Counter(props: CounterProps):
    count, set_count = create_signal(0)
    doubled = create_memo(lambda: count() * 2)

    def increment():
        set_count(lambda n: n + props.step())
        if props.on_change is not None:
            props.on_change(count.peek() + props.step.peek())

    return div(
        p(t"Count: {count} (doubled: {doubled})"),
        button("+", on_click=increment),
        Show(lambda: count() > 5, lambda: p("That's a lot of clicks.")),
    )


class PanelProps(ParentProps):
    title: Prop[str]


@component
def Panel(props: PanelProps):
    return section(h2(props.title), props.children, class_="panel")


@component
def Todos():
    store, set_store = create_store({"items": []})
    draft, set_draft = create_signal("")

    @action
    async def add(title: str):
        set_store(lambda s: s["items"].append({"id": len(s["items"]) + 1, "title": title}))
        set_draft("")

    return div(
        input_(value=draft, on_input=lambda e: set_draft(e.target.value)),
        button("Add", on_click=lambda: add(draft.peek()), disabled=add.pending),
        ul(For(lambda: store["items"], lambda item, i: li(lambda: item()["title"]), keyed=lambda t: t["id"])),
    )


@component
def App():
    return Errored(
        lambda: Loading(
            lambda: div(
                Panel(title="Counter")[Counter(step=2, on_change=print)],
                Panel(title="Todos")[Todos()],
            ),
            fallback=p("Loading..."),
        ),
        fallback=lambda err, reset: div(
            p("Something went wrong: ", lambda: str(err())),
            button("Retry", on_click=reset),
        ),
    )


render(App(), "#app")
```

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
