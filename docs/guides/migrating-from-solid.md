# Migrating from Solid

Wybthon is SolidJS for Python, and it tracks **SolidJS 2.0** semantics: async-first reactivity, automatic batching, actions and optimistic state, draft-first stores, and the `For` plus `Repeat` flow components. Nearly every primitive has a direct equivalent, and the mental model is identical: components run once, signals drive fine-grained updates, and the ownership tree manages cleanup.

The differences are mostly surface: Python instead of JavaScript, HTML helper functions instead of JSX, snake_case names, and a small number of deliberate semantic choices listed at the end.

## API mapping

| SolidJS 2.0 | Wybthon |
| --- | --- |
| `createSignal(initial)` | [`create_signal(initial)`][wybthon.create_signal] |
| `createSignal(() => derived)` (function form) | `create_signal(lambda: derived())` |
| `createMemo(fn, { equals })` | [`create_memo(fn, equals=...)`][wybthon.create_memo] |
| `createAsync(async fn)` | `create_memo(async_fn)`: an `async def` body makes an async memo |
| `createEffect(compute, apply)` | [`create_effect(compute, apply)`][wybthon.create_effect] |
| `createEffect(fn)` | `create_effect(fn)` (single function, tracked) |
| `createRenderEffect(fn)` | [`create_render_effect(fn)`][wybthon.create_render_effect] |
| `onMount(fn)` | [`on_settled(fn)`][wybthon.on_settled] |
| `onCleanup(fn)` | [`on_cleanup(fn)`][wybthon.on_cleanup] |
| `createRoot(dispose => ...)` | [`create_root(lambda dispose: ...)`][wybthon.create_root] |
| `getOwner()` / `runWithOwner(owner, fn)` | [`get_owner()`][wybthon.get_owner] / [`run_with_owner(owner, fn)`][wybthon.run_with_owner] |
| `untrack(fn)` | [`untrack(fn)`][wybthon.untrack], or `accessor.peek()` for a single read |
| `batch(fn)` | Nothing to call; every write batches until the next flush. [`flush()`][wybthon.flush] settles synchronously. |
| `isPending(fn)` | [`is_pending(fn)`][wybthon.is_pending] |
| `latest(fn)` | [`latest(fn)`][wybthon.latest] |
| `resolve(fn)` | [`await resolve(fn)`][wybthon.resolve] |
| `refresh(memo)` | [`await refresh(memo)`][wybthon.refresh] |
| `action(fn)` | [`action(fn)`][wybthon.action], usable as `@action` |
| `createOptimistic(source)` | [`create_optimistic(source)`][wybthon.create_optimistic] |
| `createOptimisticStore(source)` | [`create_optimistic_store(source)`][wybthon.create_optimistic_store] |
| `createStore(initial)` (draft setter) | [`create_store(initial)`][wybthon.create_store] |
| `reconcile(data, key)` | [`reconcile(data, key="id")`][wybthon.reconcile] |
| `createProjection(fn, initial)` | [`create_projection(fn, initial)`][wybthon.create_projection] |
| `unwrap(store)` | [`snapshot(store)`][wybthon.snapshot] |
| `<Suspense fallback>` | [`Loading(children, fallback=...)`][wybthon.Loading] |
| `<SuspenseList revealOrder tail>` | [`Reveal(children, order=..., tail=...)`][wybthon.Reveal] |
| `<ErrorBoundary fallback>` | [`Errored(children, fallback=...)`][wybthon.Errored] |
| `<Show when fallback>` | [`Show(when, children, fallback=...)`][wybthon.Show] |
| `<For each>` | [`For(each, children)`][wybthon.For] (keyed by identity) |
| `<For each key>` | `For(each, children, keyed=lambda item: ...)` |
| `<Index each>` | `For(each, children, keyed=False)` |
| `<Repeat count>` | [`Repeat(count, children)`][wybthon.Repeat] |
| `<Switch>` / `<Match when>` | [`Switch`][wybthon.Switch] / [`Match(when, children)`][wybthon.Match] |
| `<Dynamic component>` | [`Dynamic(component, **props)`][wybthon.Dynamic] |
| `<Portal mount>` | [`Portal(children, mount=...)`][wybthon.Portal] |
| `lazy(() => import(...))` | [`lazy(loader)`][wybthon.lazy] |
| `createContext(default)` | [`create_context(default)`][wybthon.create_context] |
| `<Ctx.Provider value>` | `Ctx(value, *children)`: the context object is the provider |
| `useContext(Ctx)` | [`use_context(Ctx)`][wybthon.use_context] |
| `mergeProps(a, b)` | [`merge(a, b)`][wybthon.merge] |
| `splitProps(props, keys)` | [`omit(props, *keys)`][wybthon.omit] (returns the remainder) |
| `children(() => props.children)` | [`children(props.children)`][wybthon.children] |
| `mapArray(source, fn)` | [`map_array(source, fn)`][wybthon.map_array] |
| `indexArray(source, fn)` | `map_array(source, fn, keyed=False)` |
| `createSelector(source)` | [`create_selector(source)`][wybthon.create_selector] |
| `createUniqueId()` | [`create_unique_id()`][wybthon.create_unique_id] |
| `NotReadyError` | [`NotReadyError`][wybthon.NotReadyError] |
| `props.x` (getter) | `x: Prop[T]` parameter; place `x` in the tree or call `x()` in a scope |
| `ref={el => ...}` | `ref=Ref()`; read `ref.current.element` after `on_settled` |
| JSX | HTML helpers plus holes (below) |

Solid 1.x primitives that 2.0 removed (`createResource`, `on`, `createComputed`, `createDeferred`, `produce`, `createMutable`, path-based store writes, `useTransition`) don't exist here either. The table above covers their 2.0 replacements.

## JSX becomes helpers and holes

```jsx
function Greeting(props) {
  return <p class="greeting">Hello, {props.name}{props.excited ? "!" : "."}</p>;
}
```

```python
from wybthon import Prop, component, p, prop


@component
def Greeting(name: Prop[str], excited: Prop[bool] = prop(False)):
    return p("Hello, ", name, lambda: "!" if excited() else ".", class_="greeting")
```

- Children are positional arguments; attributes are keyword arguments. Names that collide with Python keywords or builtins get a trailing underscore (`class_`, `input_`, `main_`), and `html_for` stands in for `for`.
- `{expr}` in JSX becomes a **hole**: any zero-argument callable placed in the tree. An accessor (`name`) is already a callable, so it goes in directly; wrap other expressions in `lambda:`.
- Attributes accept accessors and lambdas the same way: `class_=lambda: "on" if active() else ""`, `disabled=add.pending`.
- Event handlers are `on_click=handler`; the handler receives a [`DomEvent`][wybthon.DomEvent] with `e.target`, `e.key`, `e.prevent_default()`, and friends.
- Tag helpers exist for every HTML element (from `wybthon`) and SVG element (from [`wybthon.svg`][wybthon.svg]). For custom elements, use [`h("my-element", {...}, *children)`][wybthon.h].

## Components and props

Solid props are getters on a proxy; Wybthon props are [`Prop[T]`][wybthon.Prop] accessors bound to named parameters. The rules are the same as Solid's:

```python
from wybthon import Prop, component, div, h2, p, prop


@component
def Card(title: Prop[str], body: Prop[str] = prop(""), **rest):
    return div(h2(title), p(body), class_="card", **rest)
```

- Pass a prop straight into the tree to create a hole, or call it inside a memo, effect, or hole.
- Assigning `value = title()` at the top of the body destructures and freezes, as in Solid; dev mode warns. Use `title.peek()` when you mean it.
- `**rest` is the spread. [`merge`][wybthon.merge] and [`omit`][wybthon.omit] replace `mergeProps` and `splitProps`; both return mappings you can splat.
- A component declared with a single `props` parameter receives a [`Props`][wybthon.Props] mapping instead, the closest match to Solid's props object.

## Signals and effects

```python
from wybthon import create_effect, create_signal, flush

count, set_count = create_signal(0)


def log(value: int, prev: int | None) -> None:
    print("count =", value)


create_effect(count, log)
set_count(1)
flush()
```

The split form is Solid 2.0's `createEffect(compute, apply)`: `compute` runs tracked, `apply` runs untracked with the value and previous value, and may return a cleanup. Effects run after the DOM commit; the first run happens on the flush after the component mounted. The single-function form `create_effect(fn)` also works.

Signal semantics that carry over:

- **Automatic batching.** All writes in one turn coalesce into one flush; there's no `batch()`.
- **Glitch-free propagation.** An effect that reads several memos derived from the same signal runs once per flush and never sees an inconsistent pair.
- **Lazy memos with equality short-circuit.** `create_memo` recomputes when read after a source changed and doesn't notify if the value is equal under `equals`.
- **Async-first.** An `async def` passed to `create_memo` is an async computation. Reading it before the first value raises [`NotReadyError`][wybthon.NotReadyError] (which `Loading` catches); later recomputes serve the stale value while revalidating.

## Flow

```python
from wybthon import For, Match, Show, Switch, li, p, ul

Show(lambda: user() is not None, lambda u: p("Hello, ", lambda: u()["name"]), fallback=p("Sign in"))

ul(For(lambda: store.todos, lambda todo, i: li(lambda: todo()["title"]), keyed=lambda t: t["id"]))

Switch(
    Match(lambda: status() == "loading", lambda: p("Loading...")),
    Match(lambda: status() == "ready", lambda: p("Ready")),
    fallback=lambda: p("Unknown"),
)
```

`For` mirrors Solid's unified `For`: with `keyed=True` (the default) rows match by identity and the callback receives `(item, index_accessor)`; with a key function or `keyed=False` the callback receives `(item_accessor, index_accessor)`. Pass an accessor or a store path for `each`, not a plain list. `Repeat(count, lambda i: ...)` matches Solid 2.0's `Repeat`.

## Boundaries

```python
from wybthon import Errored, Loading, button, div, p

Errored(
    lambda: Loading(lambda: Dashboard(), fallback=p("Loading...")),
    fallback=lambda err, reset: div(p(str(err)), button("Retry", on_click=lambda e: reset())),
    reset_on=current_path,
)
```

`Loading` and `Errored` are `Suspense` and `ErrorBoundary`. The error fallback receives `(error, reset)`; `reset_on` re-mounts when the given accessor changes. [`Reveal`][wybthon.Reveal] coordinates multiple boundaries like `SuspenseList`.

## Stores

```python
from wybthon import create_store, reconcile, snapshot

state, set_state = create_store({"count": 0, "items": []})


def update(s):
    s.count += 1
    s.items.append({"id": 3, "title": "new"})


set_state(update)
set_state(reconcile({"count": 5, "items": fetched_items}, key="id"))
raw = snapshot(state.items)
```

Setters are draft-first, as in Solid 2.0. Reads are tracked at the leaf, only leaves that changed notify, and `reconcile` preserves identity by key so `For` rows keep their DOM. [`create_projection`][wybthon.create_projection] and [`create_optimistic_store`][wybthon.create_optimistic_store] match their Solid 2.0 namesakes.

## Context

```python
from wybthon import component, create_context, create_signal, p, use_context

Theme = create_context("light")


@component
def Root():
    theme, set_theme = create_signal("dark")
    return Theme(theme, Page())


@component
def Page():
    theme = use_context(Theme)
    return p(lambda: f"Theme: {theme()}")
```

There's no `.Provider`: calling the `Context` object with a value and children returns the provider node. `use_context` returns the value exactly as provided, so an accessor stays an accessor.

## Async, actions, and optimistic state

```python
from js import fetch

from wybthon import Loading, action, create_memo, create_optimistic, is_pending, p, refresh, span


async def fetch_user():
    resp = await fetch("/api/user")
    return (await resp.json()).to_py()


user = create_memo(fetch_user)

Loading(
    lambda: p(lambda: user()["name"], span(lambda: " (refreshing)" if is_pending(user) else "")),
    fallback=p("Loading..."),
)

shown, set_shown = create_optimistic(likes)


@action
async def like():
    set_shown(lambda n: n + 1)
    await post_like()
    await refresh(likes)
```

Everything here has the same name and shape as Solid 2.0, with `await` in place of promise chaining. `action.pending()` is tracked, so it works directly as `disabled=like.pending`.

## What's intentionally different

- **Naming.** snake_case across the API; component names stay PascalCase; `_` suffix on tags that collide with Python keywords or builtins.
- **A virtual DOM under the reactive graph.** Solid compiles JSX to direct DOM operations. Wybthon builds a lightweight VNode tree and a reconciler applies changes in batches through a small JS kernel. You still get fine-grained holes as the unit of update; the VDOM exists because Python can't compile templates ahead of time in the browser.
- **Staged writes.** After `set_x(1)`, `x()` returns the old value until the flush (end of the handler, or `flush()`). Solid 2.0 leans the same way; Wybthon makes it strict. Use functional updates (`set_x(lambda v: v + 1)`) to compose writes, and `create_signal`'s returned setter gives back the staged value if you need it.
- **Writes are forbidden inside tracking scopes.** Writing a signal from a memo body, a hole, or a single-function effect raises `WriteInScopeError` in dev mode. Write from handlers, actions, `on_settled`, or the `apply` stage.
- **Equality.** The default `equals` is Python `==` with an identity fast path, not `===`. Pass `equals=lambda a, b: a is b` for identity-only, `equals=False` to always notify.
- **`.peek()`.** Every accessor has `.peek()`, a one-read `untrack`.
- **`on_settled` instead of `onMount`.** The name reflects when it runs: after the flush that mounted the component committed to the DOM. It may return a cleanup.
- **Python 3.12+.** Type hints use PEP 695 generics, and the framework's own generics (`Accessor[T]`, `Prop[T]`) are meant to be written in your code.
- **JS interop through Pyodide.** `from js import fetch`, `pyodide.ffi.create_proxy` for callbacks, `.to_py()` for JS objects. See the [Pyodide guide](pyodide.md).

## What carries over directly

- The mental model: components run once, reactivity is fine-grained, ownership handles cleanup.
- The 2.0 async story: async memos, `Loading`, `is_pending`, `latest`, `resolve`, `refresh`, actions, optimistic state.
- Draft-first stores, `reconcile`, projections.
- Flow components, boundaries, context, lazy, portals.

## Next steps

- Read [Mental model](../concepts/mental-model.md) to see the formal definitions of holes and scopes.
- Explore [Authoring patterns](authoring-patterns.md); most should look familiar.
- Browse the [API reference](../api/wybthon.md) for the full set of primitives.
