# Async and loading

Async work is part of Wybthon's reactive graph. There's no separate
resource primitive: a memo whose body is `async def` *is* the async
primitive, and everything else builds on it.

- [`create_memo`][wybthon.create_memo] with an `async def` body creates an **async memo**: a derived value the graph knows may not be ready yet.
- [`Loading`][wybthon.Loading] shows a fallback while async reads under it haven't produced a first value. Its content stays mounted the whole time.
- [`Reveal`][wybthon.Reveal] coordinates several boundaries.
- [`lazy`][wybthon.lazy] defers loading a component until it mounts, backed by an async memo.
- [`action`][wybthon.action], [`create_optimistic`][wybthon.create_optimistic], and [`create_optimistic_store`][wybthon.create_optimistic_store] handle async **mutations** with instant, self-reverting UI.

## When to reach for each

| Situation | Use |
| --- | --- |
| Fetching data with a loading state | `create_memo(async_fn)` inside `Loading` |
| Inline "refreshing" hints without tearing content down | [`is_pending`][wybthon.is_pending] |
| Reading async data without suspending | [`latest`][wybthon.latest] |
| Waiting for a value in imperative code | [`resolve`][wybthon.resolve] |
| Re-asking the server after a write | [`refresh`][wybthon.refresh] |
| Streams and subscriptions | an async generator memo |
| Code-splitting a heavy route or panel | `lazy(loader)` |
| Coordinating several boundaries | `Reveal` |
| Async mutations (create, update, delete) | `@action` and optimistic state |

## Async memos

Pass an `async def` to `create_memo` and it becomes an async computation:

```python
from wybthon import create_memo, create_signal

user_id, set_user_id = create_signal(1)


async def load_user():
    uid = user_id()                       # tracked before the await
    return await fetch_json(f"/api/users/{uid}")


user = create_memo(load_user)
```

The lifecycle:

- **Before the first value**, reading `user()` raises [`NotReadyError`][wybthon.NotReadyError]. You almost never handle this yourself: the nearest `Loading` boundary turns it into fallback UI, sync memos that read a pending value become pending themselves, and a hole that hits it keeps its previous content.
- **After the first value**, recomputes serve the stale value while the new one is in flight (stale-while-revalidate). Content stays visible during refreshes, and revalidations never re-trigger a `Loading` boundary.
- **Errors** from the coroutine are stored and re-raised on read, so a failed fetch reaches the nearest [`Errored`][wybthon.Errored] boundary.

Signal reads inside the coroutine are tracked both before and after
`await`, so an async memo refetches when its inputs change. Changing
`user_id` above reruns the fetch; reading a `version` signal and bumping
it is the manual equivalent.

### Async generators

An `async def` body containing `yield` streams: each yielded value
becomes the memo's new value. Use it to adapt sockets, timers, or any
async iterable:

```python
import asyncio

from wybthon import create_memo


async def ticker():
    n = 0
    while True:
        yield n
        n += 1
        await asyncio.sleep(1)


seconds = create_memo(ticker)
```

The generator is closed when the memo re-runs or is disposed.

### Observing in-flight state

Four helpers work with async values without making you catch
`NotReadyError`:

- **`is_pending(fn)`** is a tracked probe. It's `True` while a change-triggered recompute of any async value `fn` reads is in flight, while an optimistic override is active, or when `fn` raises `NotReadyError`.
- **`latest(fn)`** evaluates `fn` without ever raising: not-ready reads return their most recent value, or `None` if they never resolved.
- **`await resolve(fn)`** returns the next settled value of `fn()` (or raises the exception it raised).
- **`await refresh(memo)`** recomputes quietly and returns the settled value. "Quiet" means `is_pending` stays `False` and readers keep the previous value while the run is in flight.

```python
from wybthon import is_pending, latest
from wybthon.html import span

span(lambda: "Refreshing..." if is_pending(user) else "")
span(lambda: (latest(user) or {}).get("name", "anonymous"))
```

## Loading

`Loading` watches its subtree for async reads that aren't ready. While
any registered computation has no value yet it shows `fallback`; once
everything has a first value it reveals the content.

```python
from wybthon import Loading, component, create_memo
from wybthon.html import div, p, span


async def fetch_user():
    return await fetch_json("/api/user")


@component
def Profile():
    user = create_memo(fetch_user)

    return Loading(
        lambda: div(
            p("Name: ", span(lambda: user()["name"])),
            p("Email: ", span(lambda: user()["email"])),
        ),
        fallback=lambda: p("Loading..."),
    )
```

- `children` may be a VNode, a zero-arg callable, or a list of either. `fallback` may be a VNode, a string, or a callable.
- Any read that raises `NotReadyError` under the boundary registers its computation automatically; there's no manual wiring.
- **Content stays mounted.** The children mount immediately and keep running while the fallback shows; their DOM nodes are parked off-document and moved back into place once everything resolves. Async memos created inside the content therefore start loading right away, and signal updates inside the parked content still apply.
- `on=` takes an accessor (or a list of them) the boundary should also wait for, even if the children never read them. Use it to keep a layout from partially rendering while a critical query is in flight:

```python
Loading(lambda: Dashboard(), fallback=Spinner(), on=[user, settings])
```

### Nesting boundaries

Nest `Loading` boundaries to refine which parts of the page show
fallbacks. The closest enclosing boundary handles each pending
computation; an inner boundary's pending reads never bubble to the outer
one.

### Coordinating boundaries with `Reveal`

When several sibling boundaries load in parallel, their contents pop in
as each resolves. Wrap them in `Reveal` to control the order and how
many fallbacks show at once:

```python
from wybthon import Loading, Reveal
from wybthon.html import p

Reveal(
    [
        Loading(lambda: ProfilePanel(), fallback=p("Loading profile...")),
        Loading(lambda: FeedPanel(), fallback=p("Loading feed...")),
        Loading(lambda: TrendsPanel(), fallback=p("Loading trends...")),
    ],
    order="forwards",
    tail="collapsed",
)
```

- `order` is `"forwards"` (top to bottom, the default; each boundary waits for the ones before it), `"backwards"`, or `"together"` (everything reveals at once).
- `tail` controls pending fallbacks: `"visible"` (all, the default), `"collapsed"` (only the next one in reveal order), or `"hidden"` (none).

Every boundary's content mounts immediately, so they all load in
parallel; `order` only controls when each is revealed.

### Errors inside a boundary

`Loading` handles loading states only. Pair it with `Errored` to catch
fetch failures and render errors:

```python
from wybthon import Errored, Loading
from wybthon.html import p

Errored(
    lambda: Loading(lambda: p(lambda: user()["name"]), fallback=p("Loading...")),
    fallback=lambda err, reset: p("Something went wrong: ", str(err)),
)
```

## Actions and optimistic state

Data fetching covers reads; **actions** cover writes. `@action` wraps a
mutation so the graph can track its in-flight state:

```python
from wybthon import action, create_memo, create_optimistic, refresh

likes = create_memo(fetch_like_count)          # async source
shown, set_shown = create_optimistic(likes)     # shadows it


@action
async def like():
    set_shown(lambda n: (n or 0) + 1)   # instant UI
    await api_like()
    await refresh(likes)                # real data lands quietly
```

- An action runs synchronously up to its first `await`, so optimistic writes at the top apply right away (visible at the next flush, like any write).
- `like.pending()` is a tracked accessor that's `True` while any invocation is in flight; use it to disable buttons or show spinners.
- Errors route to the nearest `Errored` boundary captured at call time *and* re-raise to the awaiter, so `await like()` behaves like a normal call.
- A sync function may also be wrapped; it returns its result directly and is never pending.

`create_optimistic(source)` overlays a value: `source` is an accessor to
shadow or a plain initial value. Writes through the returned setter show
immediately, and when every in-flight action has settled the override
**reverts** to the source, which by then reflects the server's answer.
While an override is active, `is_pending` reports `True` for expressions
that read it.

`create_optimistic_store(source, initial=None)` is the store version,
for nested optimistic state. `source` may be a tracked function
returning the base state (derived form, reconciled when its dependencies
change) or a plain dict or list. The setter applies draft mutations like
a [store setter](stores.md#writing-values):

```python
from wybthon import action, create_optimistic_store, create_store, deep

todos, set_todos = create_store({"items": []})
shown, set_shown = create_optimistic_store(lambda: deep(todos)["items"], [])


@action
async def add(title):
    set_shown(lambda s: s.append({"title": title, "saving": True}))
    saved = await api_create(title)
    set_todos(lambda s: s.items.append(saved))
```

## Lazy components

`lazy(loader)` returns a component backed by an async memo. The first
time it mounts (or when you call `.preload()`), the loader runs; while
it's in flight the nearest `Loading` boundary shows its fallback, and
once resolved the real component mounts in place. The result is cached
for every later mount.

```python
from wybthon import Loading, component, lazy
from wybthon.html import p

HeavyChart = lazy(lambda: ("app.heavy_chart", "Chart"))


@component
def Dashboard():
    return Loading(lambda: HeavyChart(data=chart_data), fallback=lambda: p("Loading chart..."))
```

- The loader may return a component, an imported module (`Page`, then `default`, then the first callable export is used), a module-path string, or a `(module_path, attr)` tuple.
- Async loaders can `await` work first, for example `micropip.install(...)` in Pyodide.
- A loader failure raises into the nearest `Errored` boundary.
- Call `.preload()` (for example on hover) to warm the cache before navigation.

### Lazy routes

[`Route`][wybthon.Route] accepts lazy components directly, which is the
canonical way to code-split:

```python
from wybthon import Link, Route, Router, lazy

Settings = lazy(lambda: ("app.settings", "Page"))

routes = [
    Route("/", Home),
    Route("/settings", Settings),
]

Link("Settings", href="/settings", on_mouseover=lambda e: Settings.preload())
```

## Patterns and pitfalls

- **Don't `await` async memos in render code.** Read them like any accessor; the graph handles the not-ready state. Awaiting the fetch yourself bypasses `Loading`, `is_pending`, and stale-while-revalidate. `resolve` is for imperative code such as actions and tests.
- **Create memos where the data is needed.** Because `Loading` keeps its content mounted while pending, memos created inside the content start immediately; you no longer need to hoist them above the boundary to load in parallel.
- **Prefer `refresh` after writes.** A quiet refresh keeps the current value on screen and doesn't flicker `is_pending`.
- **Keep fallbacks cheap and stable.** Avoid heavy components inside them.
- **Combine `Loading` with `Errored`.** Async work can fail. Wrap user-facing async regions with both.
- **Testing.** Drive async code with `asyncio.run(...)` and alternate `flush()` with `await asyncio.sleep(0)` so runs can start and settle. See the [Testing guide](../guides/testing.md).

## Next steps

- Read the [Async fetch example](../examples/fetch.md) for an end-to-end demo.
- See the [`loading`](../api/loading.md) API for `Loading` and `Reveal`, and [`reactivity`](../api/reactivity.md) for actions.
- Read [Error boundaries](error-boundaries.md) for `Errored`.
