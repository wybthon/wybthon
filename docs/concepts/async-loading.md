# Async and loading

Async work is part of Wybthon's reactive graph. There's no separate
resource primitive: a memo whose body is `async def` *is* the async
primitive, and everything else builds on it.

- [`create_memo`][wybthon.create_memo] with an `async def` body creates an **async memo**: a derived value the graph knows may not be ready yet.
- **Transitions** keep the screen consistent while async work is in flight: when a change makes an async memo recompute, the UI that depends on that change waits for the new value and then updates all at once.
- [`Loading`][wybthon.Loading] shows a fallback while async reads under it haven't produced a first value. Its content stays mounted the whole time.
- [`Reveal`][wybthon.Reveal] coordinates several boundaries.
- [`lazy`][wybthon.lazy] defers loading a component until it mounts, backed by an async memo.
- [`action`][wybthon.action], [`create_optimistic`][wybthon.create_optimistic], and [`create_optimistic_store`][wybthon.create_optimistic_store] handle async **mutations** as transactions with instant, self-reverting UI.

## When to reach for each

| Situation | Use |
| --- | --- |
| Fetching data with a loading state | `create_memo(async_fn)` inside `Loading` |
| Inline "refreshing" hints without tearing content down | [`is_pending`][wybthon.is_pending] |
| Showing the new input while the rest of the page waits | [`latest`][wybthon.latest] |
| Nice-to-have data that shouldn't gate anything | `create_memo(fn, loading_value=...)` |
| Waiting for a value in imperative code | [`resolve`][wybthon.resolve] |
| Re-asking the server after a write | [`refresh`][wybthon.refresh] |
| Streams and subscriptions | an async generator memo |
| Code-splitting a heavy route or panel | `lazy(loader)` |
| Coordinating several boundaries | `Reveal` |
| Async mutations (create, update, delete) | `@action` and optimistic state |
| Marking data as "changing" before a write lands | [`affects`][wybthon.affects] |
| Waiting for real data to reach a state | [`until`][wybthon.until] |

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
- **After the first value**, a recompute caused by an input change opens a **transition** (below). Readers keep the previous value while the new one is in flight, and the UI that depends on the changed input waits with it.
- **Errors** from the coroutine are stored and re-raised on read, so a failed fetch reaches the nearest [`Errored`][wybthon.Errored] boundary.

Signal reads inside the coroutine are tracked both before and after
`await`, so an async memo refetches when its inputs change. Changing
`user_id` above reruns the fetch; reading a `version` signal and bumping
it is the manual equivalent.

### `loading_value`

Some data is nice to have but shouldn't gate anything: a recommendation
panel, a badge count. Give the memo a `loading_value` and it's never
"not ready": it serves that value until the first run lands, doesn't
register with `Loading`, and never holds a transition on mount.

```python
suggestions = create_memo(load_suggestions, loading_value=[])
```

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

## Transitions

Consider a header that shows the selected user's id and a body that
shows the fetched user:

```python
div(
    h1(lambda: f"User #{user_id()}"),
    p(lambda: user()["name"]),
)
```

When `set_user_id(2)` runs, the header could update immediately while
the body still shows user 1: a torn screen. Wybthon doesn't do that. The
write to `user_id` makes `user` recompute; because `user` already had a
value and is now waiting on the network, the flush **holds** the change:
`user_id` keeps reporting `1` to the UI, the header stays on `#1`, and
when the fetch lands both update in the same commit. Nothing about the
code above asks for this; it's how every async recompute behaves.

What's held is decided per flush, structurally:

- Every write committed in a round that made an async memo (that already had a value) pending is held, along with everything derived from those writes: memos, holes, prop bindings, effects, projections, list rows.
- Writes unrelated to the pending work reveal as usual. Typing into an unrelated search box while a fetch is in flight isn't delayed.
- Effects whose compute stage read held data run their apply stage at the reveal, so `create_effect` bodies see consistent state too.
- Async memos that hadn't produced a value yet don't hold anything; they're the `Loading` boundary's job.

The transition is a single object: concurrent async work and in-flight
actions share it and settle together, and a change that arrives while
one is open joins it.

### Observing a transition

Three helpers work with in-flight state without making you catch
`NotReadyError`:

- **`is_pending(fn)`** is a tracked probe. It's `True` while any value `fn` reads is held by a transition, while an async recompute of something it reads is in flight, while an in-flight action declared it with `affects`, while an optimistic override is active on it, or when it raises `NotReadyError`. The probe's reads don't wait for the transition: an indicator has to show *during* the hold.
- **`latest(fn)`** evaluates `fn` against the newest state: held values return the value being computed, and not-ready async reads return their most recent value (or `None`). Use it for the one piece of UI that should move ahead of the rest.
- **`await resolve(fn)`** returns the next settled value of `fn()` (or raises the exception it raised). It's for imperative code.

```python
from wybthon import is_pending, latest
from wybthon.html import h1, span

h1(lambda: f"User #{latest(user_id)}")                    # moves ahead
span(lambda: "Loading..." if is_pending(user) else "")    # shows during the hold
```

A quiet **`await refresh(memo)`** recomputes without opening a
transition: `is_pending` stays `False` and readers keep the previous
value while the run is in flight. Use it after a server write to re-ask
for data.

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
- **Refreshes don't re-trigger the boundary.** Once the content has shown, a recompute is a transition (the old content stays put), not a return to the fallback.

### `on=`: a fresh boundary for a new record

Sometimes the old content *shouldn't* stay put. Navigating from user 1
to user 2 is a new page, not a refresh of the old one, and a spinner is
the honest thing to show. Name the boundary's inputs with `on=`:

```python
Loading(lambda: UserPage(), fallback=Spinner(), on=user_id)
```

The boundary waits for the `on` accessors initially even if the children
never read them, and when one of them **changes** while data under the
boundary is pending, the fallback shows again instead of the change being
held. Use it for identity changes (a route's `id`), not for refreshes.

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
    collapsed=True,
)
```

- `order` is `"sequential"` (the default: contents reveal in DOM order, each waiting for the ones before it), `"together"` (the whole group reveals at once), or `"natural"` (each boundary reveals on its own data).
- `collapsed=True` (sequential only) renders nothing for the boundaries past the current frontier, so only one fallback shows at a time.
- A `Reveal` nested inside another is one slot in the parent's order. Its boundaries wait for the parent to release the slot, then follow the inner `order`; `order="natural"` is the way to make a group count as one slot without coordinating internally.

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

An `Errored` boundary also **heals**: when any input the failing
computation read changes (the fetch's `user_id`, say), the boundary
resets and re-renders on its own. See [Error boundaries](error-boundaries.md).

## Actions and optimistic state

Data fetching covers reads; **actions** cover writes. `@action` wraps a
mutation in a transaction:

```python
from wybthon import action, create_memo, create_optimistic, refresh

likes = create_memo(fetch_like_count)          # async source
shown, set_shown = create_optimistic(likes)     # shadows it


@action
async def like():
    set_shown(lambda n: (n or 0) + 1)   # instant UI
    await api_like()
    await refresh(likes)                # real data lands; the override reverts
```

Inside an action:

- **Plain writes stage into the transaction.** Signals and stores the action writes, before or after an `await`, commit to the graph but reveal together when the action settles, as does the landing of anything it `refresh`es. Reads inside the action see the staged values.
- **Optimistic writes reveal now.** Values written through `create_optimistic` or `create_optimistic_store` show immediately and revert when the action settles.
- `like.pending()` is a tracked accessor that's `True` from the call until it settles; it reveals immediately, so bind disabled buttons and spinners to it.
- Concurrent actions share one transaction and settle together.
- Errors route to the nearest `Errored` boundary captured at call time *and* re-raise to the awaiter, so `await like()` behaves like a normal call.
- A sync function may also be wrapped; its writes reveal in the flush that commits them, and it's never pending.

`create_optimistic(source)` overlays a value: `source` is an accessor to
shadow or a plain initial value. While an override is active,
`is_pending` reports `True` for expressions that read it, and `until`
sees through it to the source. It serves for optimistic *data* (the
like count you expect the server to confirm) and for process *state*
that must show during an action (a "saving" flag).

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

### `affects` and `until`

Two helpers refine what an action reports while it's in flight:

- **`affects(*targets)`** declares which signals, memos, or stores the action is going to change. Until it settles, `is_pending` is `True` for expressions that read them, even before anything was written. Use it when the pending state belongs on the *data* (dim the record being saved) rather than on the action.
- **`await until(pred)`** resolves once `pred()` is truthy on the **authoritative** view: optimistic overrides are invisible, so it observes real data only. Inside an action, reads see the action's own staged writes; a `NotReadyError` simply waits.

```python
from wybthon import action, affects, refresh, until


@action
async def checkout(cart_id):
    affects(orders)
    order_id = await api_checkout(cart_id)
    refresh(orders)
    await until(lambda: any(o["id"] == order_id for o in orders()))
    navigate(f"/orders/{order_id}")
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

- **Don't `await` async memos in render code.** Read them like any accessor; the graph handles the not-ready state. Awaiting the fetch yourself bypasses `Loading`, `is_pending`, transitions, and stale-while-revalidate. `resolve` is for imperative code such as actions and tests.
- **Create memos where the data is needed.** Because `Loading` keeps its content mounted while pending, memos created inside the content start immediately; you don't need to hoist them above the boundary to load in parallel.
- **Let transitions do the holding.** Don't hand-roll "previous value" signals to avoid tearing; a plain async memo already gives you that. Reach for `latest` only for the piece of UI that should move early.
- **Use `on=` for identity changes, not refreshes.** A new record deserves a fallback; new data for the same record deserves a hold.
- **Prefer `refresh` after writes.** A quiet refresh keeps the current value on screen and doesn't flicker `is_pending`.
- **Keep fallbacks cheap and stable.** Avoid heavy components inside them.
- **Combine `Loading` with `Errored`.** Async work can fail. Wrap user-facing async regions with both.
- **Testing.** Drive async code with `asyncio.run(...)` and alternate `flush()` with `await asyncio.sleep(0)` so runs can start and settle. See the [Testing guide](../guides/testing.md).

## Next steps

- Read the [Async fetch example](../examples/fetch.md) for an end-to-end demo.
- See the [`loading`](../api/loading.md) API for `Loading` and `Reveal`, and [`reactivity`](../api/reactivity.md) for actions, `affects`, and `until`.
- Read [Error boundaries](error-boundaries.md) for `Errored` and healing.
