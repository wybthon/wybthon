### Async Fetch

Fetch data with an async [`create_memo`][wybthon.create_memo] and show a
loading state with [`Loading`][wybthon.Loading]. There's no separate
resource primitive: a memo whose body is `async def` *is* the async
computation.

```python
from wybthon import Loading, component, create_memo, create_signal, div, dynamic, p

@component
def FetchDemo():
    version, set_version = create_signal(0)

    async def fetch_todo():
        version()  # refetch dependency
        import js
        resp = await js.fetch("https://jsonplaceholder.typicode.com/todos/1")
        data = await resp.json()
        return str(getattr(data, "title", ""))

    todo = create_memo(fetch_todo)

    return Loading(
        fallback=p("Loading..."),
        children=lambda: p(dynamic(lambda: todo() or "")),
    )
```

Reading `todo()` inside the boundary is what wires it to `Loading`:
until the coroutine resolves for the first time, the read raises
[`NotReadyError`][wybthon.NotReadyError], and the nearest boundary
catches it and shows the fallback. Once the memo has a value, the
fallback never returns; refetches serve the previous value while the
new one loads (stale-while-revalidate).

#### Refetching

Signal reads inside the async body are tracked, both before and after
`await` points. Reading a "version" signal makes it a refetch trigger:
bump it and the memo recomputes.

```python
from wybthon import button

button("Refetch", on_click=lambda e: set_version(version() + 1))
```

The same pattern generalizes to parameters. Read `user_id()` inside the
fetcher and changing the id refetches automatically:

```python
user_id, set_user_id = create_signal(1)

async def fetch_user():
    import js
    resp = await js.fetch(f"/api/users/{user_id()}")
    return await resp.json()

user = create_memo(fetch_user)
```

#### Inline refresh hints

During a refetch the UI keeps showing the stale value, so nothing
suspends. Use [`is_pending`][wybthon.is_pending] to render an inline
hint while the recompute is in flight:

```python
from wybthon import is_pending, span

span(dynamic(lambda: "Refreshing..." if is_pending(todo) else ""))
```

To peek at an async memo from outside a `Loading` boundary without
risking a `NotReadyError`, wrap the read in
[`latest`][wybthon.latest]; unresolved computations yield `None`.

## Next steps

- Read [Async and Loading](../concepts/async-loading.md) for the full model.
- See [`create_memo`][wybthon.create_memo] for async memo semantics.
- Browse the [Error boundary example](errors.md) for failure-state UI.
