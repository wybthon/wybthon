# Async fetch

Fetch data with an async [`create_memo`][wybthon.create_memo] and show a loading state with [`Loading`][wybthon.Loading]. There's no separate resource primitive: a memo whose body is `async def` *is* the async computation.

```python
from js import fetch

from wybthon import (
    Errored,
    Loading,
    button,
    component,
    create_memo,
    create_signal,
    div,
    is_pending,
    p,
    render,
    span,
)


@component
def TodoViewer():
    todo_id, set_todo_id = create_signal(1)

    async def load_todo():
        # Reads are tracked before and after ``await``: changing ``todo_id``
        # refetches automatically.
        response = await fetch(f"https://jsonplaceholder.typicode.com/todos/{todo_id()}")
        if not response.ok:
            raise RuntimeError(f"HTTP {response.status}")
        return (await response.json()).to_py()

    todo = create_memo(load_todo)

    return div(
        button("Previous", on_click=lambda e: set_todo_id(lambda i: max(1, i - 1))),
        button("Next", on_click=lambda e: set_todo_id(lambda i: i + 1)),
        Errored(
            lambda: Loading(
                lambda: p(
                    "Todo #",
                    lambda: todo()["id"],
                    ": ",
                    lambda: todo()["title"],
                    span(lambda: " (refreshing...)" if is_pending(todo) else ""),
                ),
                fallback=p("Loading..."),
            ),
            fallback=lambda err, reset: div(p("Failed: ", str(err)), button("Retry", on_click=lambda e: reset())),
        ),
    )


render(TodoViewer(), "#app")
```

## How it works

Reading `todo()` inside the boundary is what wires it to `Loading`. Until the coroutine resolves for the first time, the read raises [`NotReadyError`][wybthon.NotReadyError]; the hole keeps its previous content and the nearest boundary shows its fallback. The content stays mounted the whole time (parked off-document), so any state created inside it survives.

Once the memo has a value, the fallback never returns. When `todo_id` changes, the memo recomputes and keeps serving the previous todo until the new one arrives (stale-while-revalidate). [`is_pending`][wybthon.is_pending] is `True` during that window, which drives the inline hint.

If `load_todo` raises, the error routes to the nearest [`Errored`][wybthon.Errored] boundary. Its `reset` callback re-renders the children, which re-reads the memo.

## Refetching

Signal reads inside the async body are dependencies, so any signal works as a refetch trigger. A "version" counter is the simplest:

```python
from wybthon import button, create_memo, create_signal

version, set_version = create_signal(0)


async def load_report():
    version()  # tracked: bumping it refetches
    return await fetch_report()


report = create_memo(load_report)

button("Refetch", on_click=lambda e: set_version(lambda v: v + 1))
```

To refetch *quietly* after a mutation, without showing a pending state, use [`refresh`][wybthon.refresh]. It returns an awaitable for the next settled value:

```python
from wybthon import action, refresh


@action
async def save_report(data):
    await post_report(data)
    await refresh(report)
```

## Reading outside a boundary

[`latest`][wybthon.latest] evaluates an expression without ever raising `NotReadyError`; unresolved computations yield `None`:

```python
from wybthon import latest, span

span(lambda: (latest(lambda: todo()["title"]) or "nothing yet"))
```

[`resolve`][wybthon.resolve] awaits the next settled value, which is handy in actions and scripts:

```python
from wybthon import resolve


async def main():
    data = await resolve(todo)
    print(data["title"])
```

## Waiting on data the children don't read

Pass `on=` to make a boundary wait for specific accessors even if nothing inside reads them, for example to keep a layout from partially rendering:

```python
from wybthon import Loading, p

Loading(lambda: p("Ready"), fallback=p("Loading..."), on=[user, settings])
```

## Next steps

- Read [Async and Loading](../concepts/async-loading.md) for the full model, including [`Reveal`][wybthon.Reveal] for coordinating several boundaries.
- See [`create_memo`][wybthon.create_memo] for async memo semantics, including async generators.
- Browse the [Error handling example](errors.md) for failure-state UI.
