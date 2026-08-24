### Demo App

The demo is served from `examples/demo/`.

- `index.html` loads `bootstrap.js`
- `bootstrap.js` loads Pyodide, mounts the library from `src/wybthon/`, and copies demo files under `/app` inside Pyodide FS, then calls `app.main.main()`

Folders under `examples/demo/app/` mirror routes and components.

#### Routing and lazy loading

Routes are defined in `examples/demo/app/routes.py`.  Components are
passed directly; the `@component` decorator handles the `(props,)`
calling convention used by the router:

```python
from app.fetch.page import FetchPage
from app.flow.page import Page as FlowPage
from app.page import Page as HomePage
from app.stores.page import Page as StoresPage
from wybthon import Route, lazy


def _AboutLazy():
    return ("app.about.page", "Page")


def _TeamLazy():
    return ("app.about.team.page", "Page")


Docs = lazy(lambda: ("app.docs.page", "Page"))


def create_routes():
    return [
        Route(path="/", component=HomePage),
        Route(
            path="/about",
            component=lazy(_AboutLazy),
            children=[
                Route(path="team", component=lazy(_TeamLazy)),
            ],
        ),
        Route(path="/fetch", component=FetchPage),
        Route(path="/flow", component=FlowPage),
        Route(path="/stores", component=StoresPage),
        Route(path="/docs/*", component=Docs),
    ]
```

Every lazy component has a `.preload()` method, so you can warm the
import cache on user intent (for example, on link hover) for snappier
transitions.

#### Async data with Loading

The Fetch page fetches data with an **async memo**: `create_memo` with
an `async def` body.  Reading the memo inside a `Loading` boundary
registers it automatically, so the fallback shows until the first value
arrives.  A refetch serves the previous value while the new one loads
(stale-while-revalidate), and `is_pending` reports the refresh:

```python
from wybthon import Loading, component, create_memo, create_signal, dynamic, is_pending, p, span


@component
def FetchPage():
    version, set_version = create_signal(0)

    async def fetch_todo():
        version()  # refetch dependency
        resp = await js.fetch("https://jsonplaceholder.typicode.com/todos/1")
        data = await resp.json()
        return f"Todo: {data.title}"

    todo = create_memo(fetch_todo)

    return div(
        Loading(
            fallback=p("Loading..."),
            children=lambda: p(dynamic(lambda: todo() or "No data")),
        ),
        p("Refreshing: ", span(dynamic(lambda: "yes" if is_pending(todo) else "no"))),
    )
```

This mirrors how you'd code-split larger apps and warm the import
cache based on intent.

#### Stores with draft mutations

The Stores page drives a todo list and nested settings through
draft-first setters: the setter hands your function a mutable draft,
you mutate it with plain Python, and only the changed leaves notify.

```python
store, set_store = create_store({"todos": [...], "next_id": 3})

def add_todo(e):
    def update(s):
        s.todos.append({"id": s.next_id, "text": f"Todo #{s.next_id}", "done": False})
        s.next_id = s.next_id + 1

    set_store(update)
```

The list renders through `For` with `key=lambda t: unwrap(t)["id"]`, so
rows keep their DOM as todos toggle and reorder.

#### Flow control

The Flow page demonstrates every flow component: `Show`,
`Switch`/`Match`, `Dynamic`, and the two list primitives.  `For` runs
keyed by reference identity by default; the `For(key="index")` demo
shows per-position slots where reversing the list updates values in
place and the DOM never moves.  The `Repeat` demo renders a star
rating: `Repeat(times=rating, children=lambda i: span("\u2605"))`
mounts and disposes tail slots as the count changes, with no list
diffing.

## Next steps

- Explore the [Examples](../examples.md) for individual feature walkthroughs.
- Read [Async and Loading](../concepts/async-loading.md).
- See the [Dev server guide](dev-server.md) for the local feedback loop.
