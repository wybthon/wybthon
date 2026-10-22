# Async fetch

Fetch data with an async [`create_memo`][wybthon.create_memo] and show a loading state with [`Loading`][wybthon.Loading]. There's no separate resource primitive: a memo whose body is `async def` *is* the async computation.

```python
from js import fetch

from wybthon import Errored, Loading, component, create_memo, create_signal, html, is_pending, refresh, render


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

    def previous():
        set_todo_id(lambda i: max(1, i - 1))

    def next_todo():
        set_todo_id(lambda i: i + 1)

    def failed(err, reset):
        def retry():
            refresh(todo)  # fetch again
            reset()  # and re-render the boundary's children

        return html(t"""
          <div>
            <p>Failed: {err()}</p>
            <button onclick={retry}>Retry</button>
          </div>
        """)

    return html(t"""
      <div>
        <button onclick={previous}>Previous</button>
        <button onclick={next_todo}>Next</button>
        <{Errored} fallback={failed}>
          <{Loading} fallback={html(t"<p>Loading...</p>")}>
            <p>
              Todo #{todo()["id"]}: {todo()["title"]}
              <span>{" (refreshing...)" if is_pending(todo) else ""}</span>
            </p>
          </{Loading}>
        </{Errored}>
      </div>
    """)


render(TodoViewer(), "#app")
```

## How it works

Reading `todo()` inside the boundary is what wires it to `Loading`. Each expression that calls `todo()` or `is_pending(...)` is dynamic, so the compiler turns it into a getter, and each becomes its own reactive hole. Until the coroutine resolves for the first time, the read raises [`NotReadyError`][wybthon.NotReadyError]; the hole keeps its previous content and the nearest boundary shows its fallback. The content stays mounted the whole time (parked off-document), so any state created inside it survives.

Once the memo has a value, the fallback never returns. When `todo_id` changes, the memo recomputes inside a transition: it keeps serving the previous todo, and the UI that read `todo_id` holds with it, until the new one arrives, so the id and the todo never disagree on screen. [`is_pending`][wybthon.is_pending] is `True` during that window, which drives the inline hint.

If `load_todo` raises, the error routes to the nearest [`Errored`][wybthon.Errored] boundary. Its fallback reads the error through the `err` accessor. The memo keeps the error until something makes it run again, so `retry` calls [`refresh`][wybthon.refresh] to fetch again and `reset` to re-render the children. Changing `todo_id` with "Previous" or "Next" also clears the error, because the boundary heals when an input of the failed computation changes.

The boundaries take nodes directly: `Errored(Loading(...))` needs no wrapping lambdas, because nothing in a node runs until it mounts inside the boundary. Written inside the template, the boundary calls are built the way component tags are, with getters for their dynamic arguments; the nested template's holes don't run until `Loading` mounts them. An interpolation can span several lines, as this one does.

## Refetching

Signal reads inside the async body are dependencies, so any signal works as a refetch trigger. A "version" counter is the simplest:

```python
from wybthon import create_memo, create_signal, html

version, set_version = create_signal(0)


async def load_report():
    version()  # tracked: bumping it refetches
    return await fetch_report()


report = create_memo(load_report)


def refetch():
    set_version(lambda v: v + 1)


html(t"<button onclick={refetch}>Refetch</button>")
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
from wybthon import html, latest


html(t"<span>{latest(lambda: todo()['title']) or 'nothing yet'}</span>")
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
from wybthon import Loading, html

Loading(html(t"<p>Ready</p>"), fallback=html(t"<p>Loading...</p>"), on=[user, settings])
```

## Next steps

- Read [Async and Loading](../concepts/async-loading.md) for the full model, including [`Reveal`][wybthon.Reveal] for coordinating several boundaries.
- See [`create_memo`][wybthon.create_memo] for async memo semantics, including async generators.
- Browse the [Error handling example](errors.md) for failure-state UI.
