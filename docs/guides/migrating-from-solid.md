# Migrating from Solid

Wybthon is essentially SolidJS for Python. Most of the primitives have direct equivalents and the mental model is identical: components run once, signals drive fine-grained updates, and the ownership tree manages cleanup.

The differences are mostly cosmetic: Python instead of JavaScript, builder functions instead of JSX, and a few naming conventions to keep things idiomatic.

## API mapping

| SolidJS | Wybthon |
| --- | --- |
| `createSignal(initial)` | [`create_signal(initial)`][wybthon.create_signal] |
| `createEffect(fn)` | [`create_effect(fn)`][wybthon.create_effect] |
| `createRenderEffect(fn)` | [`create_render_effect(fn)`][wybthon.create_render_effect] |
| `createComputed(fn)` | [`create_computed(fn)`][wybthon.create_computed] |
| `createMemo(fn, v, { equals })` | [`create_memo(fn, equals=...)`][wybthon.create_memo] |
| `createReaction(onInvalidate)` | [`create_reaction(on_invalidate)`][wybthon.create_reaction] |
| `onError(handler)` | [`on_error(handler)`][wybthon.on_error] |
| `createDeferred(source)` | [`create_deferred(source)`][wybthon.create_deferred] |
| `createUniqueId()` | [`create_unique_id()`][wybthon.create_unique_id] |
| `catchError(fn, handler)` | [`catch_error(fn, handler)`][wybthon.catch_error] |
| `createSelector(source)` | [`create_selector(source)`][wybthon.create_selector] |
| `mapArray` / `indexArray` | [`map_array`][wybthon.map_array] / [`index_array`][wybthon.index_array] |
| `mergeProps` / `splitProps` | [`merge_props`][wybthon.merge_props] / [`split_props`][wybthon.split_props] |
| `children(fn)` | [`children(fn)`][wybthon.children] |
| `getOwner` / `runWithOwner` | [`get_owner`][wybthon.get_owner] / [`run_with_owner`][wybthon.run_with_owner] |
| `createRoot(fn)` | [`create_root(fn)`][wybthon.create_root] |
| `createResource(source, fetcher)` | [`create_resource(source, fetcher)`][wybthon.create_resource] |
| `createContext(default)` / `useContext` | [`create_context`][wybthon.create_context] / [`use_context`][wybthon.use_context] |
| `Ctx.Provider` | `ctx.Provider(value=..., children=[...])` |
| `<Show when={...} fallback={...}>` | [`Show(when=..., fallback=...)`][wybthon.Show] |
| `<For each={...}>` | [`For(each=..., children=...)`][wybthon.For] |
| `<Index each={...}>` | [`Index(each=..., children=...)`][wybthon.Index] |
| `<Switch>` / `<Match>` | [`Switch`][wybthon.Switch] / [`Match`][wybthon.Match] |
| `<Dynamic component={...} />` | [`Dynamic(component=...)`][wybthon.Dynamic] |
| `<Portal mount={...}>` | [`Portal(mount=...)`][wybthon.Portal] |
| `<ErrorBoundary fallback={...}>` | [`ErrorBoundary(fallback=...)`][wybthon.ErrorBoundary] |
| `<Suspense fallback={...}>` | [`Suspense(fallback=...)`][wybthon.Suspense] |
| `<SuspenseList revealOrder={...}>` | [`SuspenseList(reveal_order=...)`][wybthon.SuspenseList] |
| `lazy(() => import(...))` | [`lazy(loader)`][wybthon.lazy] |
| `onMount(fn)` | [`on_mount(fn)`][wybthon.on_mount] |
| `onCleanup(fn)` | [`on_cleanup(fn)`][wybthon.on_cleanup] |
| `batch(fn)` | [`batch(fn)`][wybthon.batch] |
| `untrack(fn)` | [`untrack(fn)`][wybthon.untrack] |
| `on(deps, fn)` | [`on(deps, fn)`][wybthon.on] |
| `createStore(initial)` | [`create_store(initial)`][wybthon.create_store] |
| `createMutable(initial)` | [`create_mutable(initial)`][wybthon.create_mutable] |
| `modifyMutable(state, modifier)` | [`modify_mutable(state, modifier)`][wybthon.modify_mutable] |
| `produce(fn)` | [`produce(fn)`][wybthon.produce] |
| `reconcile(data)` | [`reconcile(data, key="id")`][wybthon.reconcile] |
| `unwrap(store)` | [`unwrap(store)`][wybthon.unwrap] |

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

`create_effect` re-runs whenever signals it tracked during the previous run change. There's no manual dep array.

### Execution semantics carry over

The behaviors you rely on in Solid hold in Wybthon too:

- **Synchronous updates.** Outside a `batch`, a `set` propagates before it
  returns. After `set_count(1)`, both `count()` and any derived memo read the
  new value immediately. (No `await`, no microtask, no test `sleep`.)
- **Glitch-free.** An effect reading several memos derived from one signal
  always sees a consistent combination and runs once per change, never on an
  intermediate state.
- **Lazy memos.** `create_memo` recomputes only when read after a dependency
  changed, and skips notifying consumers when its value is unchanged (same
  `equals`-based short-circuit as Solid).
- **`batch`** coalesces writes and flushes once at the outermost boundary.

`For` and `Index` match Solid exactly: the mapping callback runs **once
per unique item** (or per index slot), and its result is cached. On list
changes only added items map, removed items dispose, and reorders move
existing DOM nodes. That means eager reads like `str(item())` inside the
callback freeze at creation, just like destructuring props: pass the
accessor itself (or `dynamic(lambda: ...)`) where the value should stay
live.

## Stores

```python
from wybthon import create_store, produce, reconcile, unwrap

state, set_state = create_store({"count": 0, "items": []})

# Path-based writes:
set_state("count", lambda c: c + 1)

# Atomic multi-mutation update (Immer-style draft):
def update(s):
    s.count += 1
    s.items.append("new")

set_state(produce(update))

# Diff fresh server data in, preserving identity for unchanged items:
set_state("items", reconcile(fetched_items))

# Get the raw data back out:
raw = unwrap(state.items)
```

Stores wrap nested data in lazy proxies so reads are tracked at the leaf level, exactly like Solid.

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
- Transitions and resources: `create_resource` integrates with `Suspense`.
- Patterns like keyed lists, conditional flows, and nested boundaries.

## Next steps

- Read [Mental model](../concepts/mental-model.md) for the framework's core ideas.
- Explore [Authoring patterns](authoring-patterns.md); many should look familiar.
- Browse the [API reference](../api/wybthon.md) for the full set of primitives.
