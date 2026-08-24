# Async and Loading

Async work is a first-class part of Wybthon's reactive graph. There's no separate resource primitive: a memo whose body is an `async def` *is* the async primitive, and everything else builds on it.

- [`create_memo`][wybthon.create_memo] with an `async def` body creates an **async memo**: a derived value the graph knows may not be ready yet.
- [`Loading`][wybthon.Loading] renders a fallback (e.g., a spinner) while async reads under it haven't produced their first value.
- [`LoadingList`][wybthon.LoadingList] coordinates several boundaries.
- [`lazy`][wybthon.lazy] defers loading a component module until it mounts, backed by an async memo.
- [`action`][wybthon.action], [`create_optimistic`][wybthon.create_optimistic], and [`create_optimistic_store`][wybthon.create_optimistic_store] handle async **mutations** with instant, self-reverting UI.

## When to reach for each

| Situation | Use |
| --- | --- |
| Async data fetching with a loading state | `create_memo(async_fn)` + `Loading` |
| Inline "refreshing" hints without tearing content down | [`is_pending`][wybthon.is_pending] |
| Reading async data without suspending | [`latest`][wybthon.latest] |
| Code-splitting a heavy route or panel | `lazy(loader)` inside a route |
| Coordinating several boundaries | `LoadingList` |
| Async mutations (create, update, delete) | `@action` + optimistic state |

## Async memos

Pass an `async def` to `create_memo` and it becomes an async computation:

```python
from wybthon import create_memo

async def fetch_user():
    resp = await js.fetch("/api/user")
    return await resp.json()

user = create_memo(fetch_user)
```

The lifecycle:

- **Before the first value**, reading `user()` raises [`NotReadyError`][wybthon.NotReadyError]. You almost never handle this yourself: the nearest `Loading` boundary turns it into fallback UI, derived sync memos propagate the not-ready state, and effects that read a pending value suspend until it lands.
- **After the first value**, recomputes serve the stale value while the new one is in flight (stale-while-revalidate), so content stays visible during refreshes and revalidations never re-trigger a `Loading` boundary.
- **Errors** from the coroutine are stored and re-raised on read, so a failed fetch hits the nearest [`ErrorBoundary`][wybthon.ErrorBoundary] when the memo is read during render.

Signal reads inside the coroutine are tracked, both before and after `await` points. That gives you refetching for free: read a signal in the fetcher, and bump it to revalidate.

```python
from wybthon import create_signal, create_memo

version, set_version = create_signal(0)

async def fetch_todo():
    version()  # tracked: bumping the version refetches
    resp = await js.fetch(url)
    return await resp.json()

todo = create_memo(fetch_todo)

def refetch(_evt):
    set_version(lambda v: v + 1)
```

The same works with data-driven dependencies, such as an id signal read before the `await`.

### Observing in-flight state

Two helpers observe async state without suspending:

- `is_pending(getter)` is a **tracked** read that returns `True` while any async computation read by the getter has a recompute in flight. Use it for inline refresh hints.
- `latest(getter)` reads without ever raising `NotReadyError`: it returns the stale value, or `None` before the first value. Use it to peek at data outside a `Loading` boundary or to render optional UI that shouldn't suspend.

```python
from wybthon import is_pending, latest
from wybthon.html import span

span(lambda: "Refreshing..." if is_pending(user) else "")
span(lambda: (latest(user) or {}).get("name", "anonymous"))
```

## Loading

`Loading` watches its subtree for async reads that aren't ready. While any registered computation has no value yet, it renders `fallback`; once everything has produced a first value, it swaps to the content. Later revalidations don't re-trigger the boundary.

```python
from wybthon import Loading, component, create_memo, dynamic
from wybthon.html import div, p, span


async def fetch_user():
    resp = await js.fetch("/api/user")
    return await resp.json()


@component
def Profile():
    user = create_memo(fetch_user)

    return Loading(
        fallback=lambda: p("Loading..."),
        children=lambda: div(
            p("Name: ", span(dynamic(lambda: user()["name"]))),
            p("Email: ", span(dynamic(lambda: user()["email"]))),
        ),
    )
```

- Any read that raises `NotReadyError` under the boundary registers the computation automatically; no manual wiring is needed.
- `fallback` accepts a `VNode`, a string, or a callable, so the placeholder can stay reactive too.
- Async memos resolve independently; `Loading` waits for *all* of them.
- `Loading` and `LoadingList` are browser-only exports, from the module `wybthon.loading`.

### Nesting boundaries

You can nest `Loading` boundaries to refine which parts of the page show fallbacks. The closest enclosing boundary always wins for a given pending computation.

### Coordinating boundaries with `LoadingList`

When several sibling boundaries load in parallel, their contents pop in whenever each resolves, which can feel chaotic. Wrap them in `LoadingList` to control the reveal order and how many fallbacks show at once:

```python
from wybthon import Loading, LoadingList
from wybthon.html import p

LoadingList(
    reveal_order="forwards",
    tail="collapsed",
    children=[
        Loading(fallback=p("Loading profile..."), children=[ProfilePanel()]),
        Loading(fallback=p("Loading feed..."), children=[FeedPanel()]),
        Loading(fallback=p("Loading trends..."), children=[TrendsPanel()]),
    ],
)
```

- `reveal_order` is `"forwards"` (top-to-bottom, the default), `"backwards"`, or `"together"` (everything reveals at once).
- `tail` controls pending fallbacks: `None` (show all), `"collapsed"` (only the next one in reveal order), or `"hidden"` (none).

### Errors inside a boundary

`Loading` only handles loading states. Pair it with [`ErrorBoundary`][wybthon.ErrorBoundary] to also catch fetch failures and render errors:

```python
ErrorBoundary(
    fallback=lambda err, reset: p("Something went wrong: ", str(err)),
    children=lambda: Loading(
        fallback=lambda: p("Loading..."),
        children=lambda: p(dynamic(lambda: user()["name"])),
    ),
)
```

## Actions and optimistic state

Data fetching covers reads; **actions** cover writes. `@action` wraps an async mutation so the graph can track its in-flight state:

```python
from wybthon import action, create_optimistic, create_signal

todos, set_todos = create_signal([])
shown, set_shown = create_optimistic(todos)

@action
async def add_todo(title):
    set_shown(lambda cur: cur + [title])   # instant UI
    saved = await api_create(title)
    set_todos(todos() + [saved])           # real data lands
```

- `add_todo.pending()` is a **tracked** getter that's `True` while any run of the action is in flight; use it to disable buttons or show spinners.
- Errors route to the nearest error-boundary scope captured at call time **and** re-raise to the awaiter, so `await add_todo(...)` behaves like a normal Python call.

`create_optimistic(source)` overlays a signal: `source` is either a getter to shadow or a plain initial value. Writes through the returned setter show immediately, and when all in-flight actions have settled, the value **reverts to the source**, which by then reflects the server's answer. The optimistic overlay bridges the latency gap; you never clean it up by hand.

`create_optimistic_store(source, initial=None)` is the store version, for nested optimistic state. `source` may be a tracked function returning base state (derived form; it re-runs and reconciles when its dependencies change) or a plain dict/list (value form). The setter applies draft mutations, like a [store setter](stores.md#writing-values):

```python
from wybthon import action, create_optimistic_store, create_store, unwrap

todos, set_todos = create_store({"items": []})
shown, set_shown = create_optimistic_store(lambda: unwrap(todos)["items"], [])

@action
async def add(title):
    set_shown(lambda s: s.append({"title": title, "saving": True}))
    saved = await api_create(title)
    set_todos(lambda s: s.items.append(saved))
```

## Lazy components

`lazy(loader)` returns a placeholder component backed by an async memo. The first time it mounts, the loader runs (awaited when async); while it's in flight the nearest `Loading` boundary shows its fallback, and once resolved the real component mounts in place.

```python
from wybthon import Loading, component, lazy
from wybthon.html import p


HeavyChart = lazy(lambda: ("app.heavy_chart", "Chart"))


@component
def Dashboard():
    return Loading(
        fallback=lambda: p("Loading chart..."),
        children=lambda: HeavyChart(data=...),
    )
```

- The loader may return a component callable, an imported module, a module-path string, or a `(module_path, attr)` tuple.
- Async loaders can `await` arbitrary work first (e.g., `micropip.install(...)`) before returning the component.
- Pair `lazy` with `Loading` so users see a fallback instead of an empty space.
- Call `.preload()` on the lazy component to warm the cache (e.g., on hover) before the user actually navigates.
- A loader failure raises into the nearest [`ErrorBoundary`][wybthon.ErrorBoundary].

### Lazy routes

[`Route`][wybthon.Route] accepts lazy components directly, which is the canonical way to code-split:

```python
from wybthon import Route, Router, lazy


routes = [
    Route(path="/", component=Home),
    Route(path="/settings", component=lazy(lambda: ("app.settings", "Page"))),
]


@component
def App():
    return Router(routes=routes)
```

The first time a user visits `/settings`, the module is fetched and cached.

## Patterns and pitfalls

- **Show *something* immediately.** Loading fallbacks should be cheap and stable; avoid placing heavy components inside them.
- **Don't `await` async memos.** Read them like any getter; the graph handles the not-ready state. Awaiting the fetch yourself bypasses `Loading`, `is_pending`, and stale-while-revalidate.
- **Start memos above the boundary when parallel loading matters.** A boundary whose content hasn't mounted yet hasn't started its async computations, so sequential boundaries load as a cascade. Create the memos outside and pass them down as props to load in parallel.
- **Cache module loads.** `lazy` caches the resolved component automatically; don't call `lazy()` inside the render path.
- **Combine with `ErrorBoundary`.** Async work can fail. Always wrap user-facing async regions with both boundaries.

## Next steps

- Read the [Async fetch example](../examples/fetch.md) for an end-to-end demo.
- See the [`loading`][wybthon.loading] API for `Loading` and `LoadingList`.
- Read [Performance](../guides/performance.md) for code-splitting tips.
