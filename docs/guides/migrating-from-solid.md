# Migrating from Solid

Wybthon is essentially SolidJS for Python, and it tracks **SolidJS 2.0** semantics: async-first reactivity, automatic batching, actions and optimistic state, draft-first stores, and the unified `For` plus `Repeat` flow components. Most of the primitives have direct equivalents, and the mental model is identical: components run once, signals drive fine-grained updates, and the ownership tree manages cleanup.

The differences are mostly cosmetic: Python instead of JavaScript, builder functions instead of JSX, and a few naming conventions to keep things idiomatic.

## API mapping

| SolidJS 2.0 | Wybthon |
| --- | --- |
| `createSignal(initial)` | [`create_signal(initial)`][wybthon.create_signal] |
| `createEffect(fn)` | [`create_effect(fn)`][wybthon.create_effect] |
| `createEffect(compute, apply)` | [`create_effect(compute, apply)`][wybthon.create_effect] |
| `createRenderEffect(fn)` | [`create_render_effect(fn)`][wybthon.create_render_effect] |
| `createMemo(fn, { equals })` (async supported) | [`create_memo(fn, equals=...)`][wybthon.create_memo] |
| `isPending(getter)` | [`is_pending(getter)`][wybthon.is_pending] |
| `latest(getter)` | [`latest(getter)`][wybthon.latest] |
| `action(fn)` | [`action(fn)`][wybthon.action] |
| `createOptimistic(source)` | [`create_optimistic(source)`][wybthon.create_optimistic] |
| `createProjection(fn)` | [`create_projection(fn)`][wybthon.create_projection] |
| `createReaction(onInvalidate)` | [`create_reaction(on_invalidate)`][wybthon.create_reaction] |
| `onError(handler)` | [`on_error(handler)`][wybthon.on_error] |
| `createUniqueId()` | [`create_unique_id()`][wybthon.create_unique_id] |
| `catchError(fn, handler)` | [`catch_error(fn, handler)`][wybthon.catch_error] |
| `createSelector(source)` | [`create_selector(source)`][wybthon.create_selector] |
| `mapArray` / `indexArray` | [`map_array`][wybthon.map_array] / [`index_array`][wybthon.index_array] |
| `mergeProps` / `splitProps` | [`merge_props`][wybthon.merge_props] / [`split_props`][wybthon.split_props] |
| `children(fn)` | [`children(fn)`][wybthon.children] |
| `getOwner` / `runWithOwner` | [`get_owner`][wybthon.get_owner] / [`run_with_owner`][wybthon.run_with_owner] |
| `createRoot(fn)` | [`create_root(fn)`][wybthon.create_root] |
| `createContext(default)` / `useContext` | [`create_context`][wybthon.create_context] / [`use_context`][wybthon.use_context] |
| `Ctx.Provider` | `ctx.Provider(value=..., children=[...])` |
| `<Show when={...} fallback={...}>` | [`Show(when=..., fallback=...)`][wybthon.Show] |
| `<For each={...}>` | [`For(each=..., children=...)`][wybthon.For] |
| `<Repeat times={...}>` | [`Repeat(times=..., children=...)`][wybthon.Repeat] |
| `<Switch>` / `<Match>` | [`Switch`][wybthon.Switch] / [`Match`][wybthon.Match] |
| `<Dynamic component={...} />` | [`Dynamic(component=...)`][wybthon.Dynamic] |
| `<Portal mount={...}>` | [`Portal(mount=...)`][wybthon.Portal] |
| `<ErrorBoundary fallback={...}>` | [`ErrorBoundary(fallback=...)`][wybthon.ErrorBoundary] |
| `<Loading fallback={...}>` | [`Loading(fallback=...)`][wybthon.Loading] |
| `<LoadingList revealOrder={...}>` | [`LoadingList(reveal_order=...)`][wybthon.LoadingList] |
| `lazy(() => import(...))` | [`lazy(loader)`][wybthon.lazy] |
| `onMount(fn)` | [`on_mount(fn)`][wybthon.on_mount] |
| `onCleanup(fn)` | [`on_cleanup(fn)`][wybthon.on_cleanup] |
| `untrack(fn)` | [`untrack(fn)`][wybthon.untrack] |
| `createStore(initial)` (draft setter) | [`create_store(initial)`][wybthon.create_store] |
| `reconcile(data)` | [`reconcile(data, key="id")`][wybthon.reconcile] |
| `unwrap(store)` | [`unwrap(store)`][wybthon.unwrap] |

## Coming from Solid 1.x

Wybthon follows SolidJS 2.0, so the primitives that Solid 2.0 removed don't exist here either:

| Solid 1.x | Wybthon equivalent |
| --- | --- |
| `batch(fn)` | Nothing to call. Batching is automatic; every write batches until the next flush. Use [`flush()`][wybthon.flush] to settle effects synchronously. |
| `on(deps, fn, { defer })` | Split effects: [`create_effect(compute, apply)`][wybthon.create_effect]. The tracked `compute` phase declares dependencies; the untracked `apply` phase receives its return value. |
| `createComputed(fn)` | [`create_memo`][wybthon.create_memo] for derived values, or [`create_render_effect`][wybthon.create_render_effect] for pre-render side effects. |
| `createDeferred(source)` | Removed with no direct replacement. |
| `createResource(source, fetcher)` | Async memos: [`create_memo(async_fn)`][wybthon.create_memo], observed with [`is_pending`][wybthon.is_pending] and [`latest`][wybthon.latest]. |
| `<Suspense>` / `<SuspenseList>` | [`Loading`][wybthon.Loading] / [`LoadingList`][wybthon.LoadingList]. |
| `<Index each={...}>` | [`For(each=..., key="index")`][wybthon.For]. |
| `produce(fn)` | The store setter is draft-first: pass the mutator function directly, `set_store(fn)`. |
| `createMutable` / `modifyMutable` | Draft-first store setters via [`create_store`][wybthon.create_store]. |
| Path-based store writes (`setStore("a", "b", value)`) | Draft mutations: `set_store(lambda s: ...)` or `set_store(reconcile(data))`. |
| `useTransition` / `startTransition` | [`action`][wybthon.action] plus [`create_optimistic`][wybthon.create_optimistic] / [`create_optimistic_store`][wybthon.create_optimistic_store]. |

## Templates

Solid uses JSX. Wybthon uses Python builders from [`wybthon.html`][wybthon.html]:

```jsx
function Greeting(props) {
  return <p>Hello, {props.name}!</p>;
}
```

```python
from wybthon import component
from wybthon.html import p

@component
def Greeting(name):
    return p("Hello, ", name, "!")
```

Tag helpers are defined for every standard HTML element. For custom elements, use [`h`][wybthon.h] directly.

## Props

Solid props are reactive *getters* on a proxy object. Wybthon props arrive as **callables**:

```python
@component
def Card(title, body):
    return div(h2(title), p(body))
```

You can pass `title` straight through (creating a reactive hole) or read `title()` inside an effect. Destructuring (assigning the value to a local) freezes it at mount, just like Solid.

For ergonomic prop manipulation Wybthon offers [`merge_props`][wybthon.merge_props] and [`split_props`][wybthon.split_props], matching Solid's helpers of the same name:

```python
from wybthon import component, merge_props, split_props
from wybthon.html import button

@component
def Button(props):
    final = merge_props({"variant": "solid"}, props)
    local, rest = split_props(final, ["label", "variant"])
    return button(local["label"], class_=lambda: f"btn-{local['variant']}")
```

## Signals and effects

Identical in spirit and behavior:

```python
count, set_count = create_signal(0)
create_effect(lambda: print("count =", count()))
```

`create_effect` re-runs whenever signals it tracked during the previous run change. There's no manual dep array. Like Solid 2.0, effects also come in a split form, `create_effect(compute, apply)`: the `compute` phase runs tracked, and its return value is passed to the untracked `apply` phase, replacing 1.x's `on(deps, fn)`. Effect bodies may be `async def`; reads after an `await` are still tracked.

### Execution semantics carry over

The behaviors you rely on in Solid 2.0 hold in Wybthon too:

- **Automatic batching.** Signal writes apply immediately (reads see the
  new value right away), but effects are scheduled and run on the next
  flush: a browser microtask, automatically at the end of each Wybthon
  event handler, or an explicit [`flush()`][wybthon.flush]. Multiple
  writes coalesce into one effect run per flush; there's no `batch()`
  to call.
- **Glitch-free.** An effect reading several memos derived from one signal
  always sees a consistent combination and runs once per flush, never on an
  intermediate state.
- **Lazy memos.** `create_memo` recomputes only when read after a dependency
  changed, and skips notifying consumers when its value is unchanged (same
  `equals`-based short-circuit as Solid).
- **Async-first.** `create_memo` accepts `async def` functions. Reading
  an async memo before its first value raises
  [`NotReadyError`][wybthon.NotReadyError] (which
  [`Loading`][wybthon.Loading] boundaries catch); after the first value,
  recomputes serve the stale value while revalidating.

`For` matches Solid exactly: the mapping callback runs **once per unique
item**, and its result is cached. On list changes only added items map,
removed items dispose, and reorders move existing DOM nodes. Pass
`key="index"` for per-position slots (Solid 1.x's `Index`). That means
eager reads like `str(item())` inside the callback freeze at creation,
just like destructuring props: pass the accessor itself (or
`dynamic(lambda: ...)`) where the value should stay live.

## Stores

Stores are draft-first, matching Solid 2.0's `createStore`: the setter takes a function that mutates a draft with plain Python.

```python
from wybthon import create_store, reconcile, unwrap

state, set_state = create_store({"count": 0, "items": []})

# Atomic multi-mutation update (Immer-style draft):
def update(s):
    s.count += 1
    s.items.append("new")

set_state(update)

# Diff fresh server data in, preserving identity for unchanged items:
set_state(reconcile({"count": 5, "items": fetched_items}, key="id"))

# Get the raw data back out:
raw = unwrap(state.items)
```

Stores wrap nested data in lazy proxies so reads are tracked at the leaf level, exactly like Solid. Only the leaves your draft function actually changed notify. For read-only derived stores updated fine-grained, use [`create_projection`][wybthon.create_projection], the counterpart of Solid 2.0's `createProjection`.

## Async data, actions, and optimistic state

Solid 2.0's async model carries over directly. An async memo is the unit of async data:

```python
async def fetch_user():
    resp = await js.fetch("/api/user")
    return await resp.json()

user = create_memo(fetch_user)

Loading(
    fallback=lambda: p("Loading..."),
    children=lambda: p(dynamic(lambda: user().name)),
)
```

[`is_pending(user)`][wybthon.is_pending] reports in-flight recomputation (tracked), and [`latest(user)`][wybthon.latest] reads without raising. For mutations, [`@action`][wybthon.action] wraps an async function, exposes a tracked `.pending()` getter, and routes errors to the nearest error boundary; [`create_optimistic`][wybthon.create_optimistic] and [`create_optimistic_store`][wybthon.create_optimistic_store] overlay temporary values that revert when in-flight actions settle.

## Routing

```python
from wybthon import Route, Router, Link

routes = [
    Route(path="/", component=Home),
    Route(path="/users/:id", component=User),
]

@component
def App():
    return Router(routes=routes)
```

Wybthon's router supports nested routes, dynamic params, query parsing, and lazy components; see [Routing][wybthon.Router].

## What's intentionally different

- **Naming.** snake_case across the API (`create_signal`, not `createSignal`). Component names stay PascalCase.
- **Signal equality.** The default `equals` policy is Python value equality (`==` with an identity fast path), not JS `===`. Pass `equals=lambda a, b: a is b` when you want identity-only semantics, or `equals=False` to always notify.
- **Untracked reads.** Signal and memo getters expose `.peek()` (`count.peek()`), a shorthand for `untrack(count)`.
- **Imports.** Pull from `wybthon` (and optionally `wybthon.html` for tag helpers).
- **`Dynamic`.** Use `dynamic(lambda: ...)` to inline a reactive computation; component-style `Dynamic` exists too.
- **JS interop.** Use `pyodide.ffi` to talk to the host. See [Pyodide guide](pyodide.md).

## What carries over directly

- The mental model (components run once, fine-grained reactivity).
- Ownership semantics: `on_cleanup` attaches to the current owner.
- Async loading UI: async memos integrate with `Loading` boundaries.
- Patterns like keyed lists, conditional flows, and nested boundaries.

## Next steps

- Read [Mental model](../concepts/mental-model.md) for the framework's core ideas.
- Explore [Authoring patterns](authoring-patterns.md); many should look familiar.
- Browse the [API reference](../api/wybthon.md) for the full set of primitives.
