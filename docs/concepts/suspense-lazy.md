# Suspense and Lazy Loading

Wybthon ships two complementary primitives for asynchronous UI:

- [`Suspense`][wybthon.Suspense] renders a fallback (e.g., spinner) while a subtree is loading.
- [`lazy`][wybthon.lazy] defers loading a component module until it actually mounts.

Together they let you split big apps into smaller chunks and present a polished loading experience.

## When to reach for each

| Situation | Use |
| --- | --- |
| Async data fetching with a loading state | [`create_resource`][wybthon.create_resource] + `Suspense` |
| Code-splitting a heavy route or panel | `lazy(loader)` inside a route |
| Both at once | `lazy` *inside* a `Suspense` boundary |
| Coordinating several boundaries | [`SuspenseList`][wybthon.SuspenseList] |

## Suspense

`Suspense` watches its descendants for any tracked async work (typically a `create_resource` that hasn't resolved). While anything is pending, it renders `fallback`. Once everything resolves, it swaps to the resolved tree.

```python
from wybthon import (
    Suspense, component, create_resource, create_signal,
)
from wybthon.html import div, p, span


async def fetch_user(id_: int) -> dict:
    ...


@component
def UserCard(id):
    user = create_resource(id, fetch_user)

    return div(
        p("Name: ", span(lambda: user()["name"])),
        p("Email: ", span(lambda: user()["email"])),
    )


@component
def Profile():
    id_, _ = create_signal(42)
    return Suspense(
        fallback=lambda: p("Loading…"),
        children=lambda: UserCard(id=id_),
    )
```

- The `Suspense` boundary catches any pending resources in its subtree.
- `fallback` accepts a callable so the placeholder can stay reactive too.
- Resources resolve independently; `Suspense` waits for *all* of them.

### Nesting boundaries

You can nest `Suspense` boundaries to refine which parts of the page show fallbacks. The closest enclosing boundary always wins for a given pending resource.

### Coordinating boundaries with `SuspenseList`

When several sibling boundaries load in parallel, their contents pop in
whenever each resolves, which can feel chaotic. Wrap them in
[`SuspenseList`][wybthon.SuspenseList] to control the reveal order and
how many fallbacks show at once:

```python
from wybthon import Suspense, SuspenseList
from wybthon.html import p

SuspenseList(
    reveal_order="forwards",
    tail="collapsed",
    children=[
        Suspense(fallback=p("Loading profile…"), children=[ProfilePanel()]),
        Suspense(fallback=p("Loading feed…"), children=[FeedPanel()]),
        Suspense(fallback=p("Loading trends…"), children=[TrendsPanel()]),
    ],
)
```

- `reveal_order` is `"forwards"` (top-to-bottom, the default),
  `"backwards"`, or `"together"` (everything reveals at once).
- `tail` controls pending fallbacks: `None` (show all), `"collapsed"`
  (only the next one in reveal order), or `"hidden"` (none).

### Errors inside a boundary

`Suspense` only handles loading states. Pair it with [`ErrorBoundary`][wybthon.ErrorBoundary] to also catch render errors:

```python
ErrorBoundary(
    fallback=lambda err, reset: p("Something went wrong: ", str(err)),
    children=lambda: Suspense(
        fallback=lambda: p("Loading…"),
        children=lambda: UserCard(id=id_),
    ),
)
```

## Lazy components

`lazy(loader)` returns a placeholder component backed by a
[`Resource`][wybthon.Resource]. The first time it mounts, the loader
runs (awaited when async); while it's in flight the nearest `Suspense`
boundary shows its fallback, and once resolved the real component
mounts in place.

```python
from wybthon import Suspense, component, lazy
from wybthon.html import p


HeavyChart = lazy(lambda: ("app.heavy_chart", "Chart"))


@component
def Dashboard():
    return Suspense(
        fallback=lambda: p("Loading chart…"),
        children=lambda: HeavyChart(data=...),
    )
```

- The loader may return a component callable, an imported module, a module-path string, or a `(module_path, attr)` tuple.
- Async loaders can `await` arbitrary work first (e.g., `micropip.install(...)`) before returning the component.
- Pair `lazy` with `Suspense` so users see a fallback instead of an empty space.
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

- **Show *something* immediately.** Suspense fallbacks should be cheap and stable; avoid placing heavy components inside them.
- **Don't double-await.** A `create_resource` already integrates with `Suspense`; you don't need to `await` its value before rendering.
- **Cache module loads.** `lazy` caches the resolved component automatically; don't call `lazy()` inside the render path.
- **Combine with `ErrorBoundary`.** Async loads can fail. Always wrap user-facing lazy regions with both boundaries.

## Next steps

- Read the [Async fetch example](../examples/fetch.md) for an end-to-end resource demo.
- See [`create_resource`][wybthon.create_resource] for the resource lifecycle.
- Read [Performance](../guides/performance.md) for code-splitting tips.
