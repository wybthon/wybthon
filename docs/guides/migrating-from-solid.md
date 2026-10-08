# Migrating from Solid

Wybthon is SolidJS for Python, and it tracks **SolidJS 2.0** (release candidate 14) semantics: async-first reactivity, automatic batching, actions and optimistic state, draft-first stores, and the `For` plus `Repeat` flow components. Nearly every primitive has a direct equivalent, and the mental model is identical: components run once, signals drive fine-grained updates, and the ownership tree manages cleanup.

The differences are mostly surface: Python instead of JavaScript, HTML helper functions and t-strings instead of JSX, a `Props` class instead of a props interface, snake_case names, and a small number of deliberate semantic choices listed at the end.

## API mapping

The table follows **Solid 2.0 RC.14**.

| SolidJS 2.0 | Wybthon |
| --- | --- |
| `createSignal(initial)` | [`create_signal(initial)`][wybthon.create_signal] |
| `createSignal(() => derived)` (function form) | `create_signal(lambda: derived())` |
| `createMemo(fn, { equals })` | [`create_memo(fn, equals=...)`][wybthon.create_memo] |
| `createAsync(async fn)` | `create_memo(async_fn)`: an `async def` body makes an async memo |
| `createEffect(compute, apply)` | [`create_effect(compute, apply)`][wybthon.create_effect] |
| `createEffect(fn)` | `create_tracked_effect(fn)` (single function, tracked) |
| `createRenderEffect(compute, apply)` | [`create_render_effect(compute, apply)`][wybthon.create_render_effect] |
| `createReaction(effect)` | [`create_reaction(effect)`][wybthon.create_reaction] returns `track(fn)` |
| `onMount(fn)` | [`on_settled(fn)`][wybthon.on_settled] |
| `onCleanup(fn)` | [`on_cleanup(fn)`][wybthon.on_cleanup] |
| `createRoot(dispose => ...)` | [`create_root(lambda dispose: ...)`][wybthon.create_root] |
| `getOwner()` / `runWithOwner(owner, fn)` | [`get_owner()`][wybthon.get_owner] / [`run_with_owner(owner, fn)`][wybthon.run_with_owner] |
| `createOwner()` / `isDisposed(owner)` | [`create_owner()`][wybthon.create_owner] / [`is_disposed(owner)`][wybthon.is_disposed] |
| `untrack(fn)` | [`untrack(fn)`][wybthon.untrack], or `accessor.peek()` for a single read |
| `batch(fn)` | Nothing to call; every write batches until the next flush. [`flush()`][wybthon.flush] settles synchronously. |
| `flush()` / `flush(fn)` | [`flush()`][wybthon.flush] / `flush(fn)` |
| `createSignal(v, { ownedWrite: true })` | `create_signal(v, owned_write=True)` |
| `isPending(fn)` | [`is_pending(fn)`][wybthon.is_pending] |
| `latest(fn)` | [`latest(fn)`][wybthon.latest] |
| `resolve(fn)` | [`await resolve(fn)`][wybthon.resolve] |
| `refresh(memo)` | [`await refresh(memo)`][wybthon.refresh] |
| `action(fn)` | [`action(fn)`][wybthon.action], usable as `@action` |
| `createOptimistic(source)` | [`create_optimistic(source)`][wybthon.create_optimistic] |
| `createOptimisticStore(source)` | [`create_optimistic_store(source)`][wybthon.create_optimistic_store] |
| `affects(...)` | [`affects(...)`][wybthon.affects] |
| `until(pred)` | [`await until(pred)`][wybthon.until] |
| `TimeoutError` | `until(..., timeout=...)` raises the built-in `TimeoutError` |
| `createMemo(fn, { loadingValue })` | `create_memo(fn, loading_value=...)` |
| `NotReadyError` | [`NotReadyError`][wybthon.NotReadyError] |
| `createStore(initial)` (draft setter) | [`create_store(initial)`][wybthon.create_store] |
| `reconcile(value, key)` | [`reconcile(value, key="id")`][wybthon.reconcile]; `key` may be a string, a function, or `None` |
| `createProjection(fn, initial)` | [`create_projection(fn, initial)`][wybthon.create_projection] |
| `createSelector(source)` (removed in 2.0) | A projection: `create_projection(lambda: {} if sel() is None else {sel(): True})`, then `is_selected.get(key)` |
| `unwrap(store)` | [`snapshot(store)`][wybthon.snapshot] |
| `mapArray(list, fn, { fallback })` | [`map_array(list, fn, fallback=...)`][wybthon.map_array] |
| `indexArray(list, fn)` | `map_array(list, fn, keyed=False)` |
| `repeat(count, fn, { from, fallback })` | [`repeat(count, fn, start=..., fallback=...)`][wybthon.repeat] |
| `<Loading fallback>` (was `Suspense`) | [`Loading(children, fallback=...)`][wybthon.Loading] |
| `<Reveal order collapsed>` (was `SuspenseList`) | [`Reveal(children, order=..., collapsed=...)`][wybthon.Reveal] |
| `<Errored fallback={(err, reset) => ...}>` | [`Errored(children, fallback=lambda err, reset: ...)`][wybthon.Errored]; `err` is an accessor, so call `err()` |
| `<Show when fallback>` | [`Show(when, children, fallback=...)`][wybthon.Show] |
| `<For each>` | [`For(each, children)`][wybthon.For] (keyed by identity) |
| `<For each keyed={fn}>` | `For(each, children, keyed=lambda item: ...)` |
| `<For each keyed={false}>` (was `Index`) | `For(each, children, keyed=False)` |
| `<Repeat count>` | [`Repeat(count, children)`][wybthon.Repeat] |
| `<Switch>` / `<Match when>` | [`Switch`][wybthon.Switch] / [`Match(when, children)`][wybthon.Match] |
| `dynamic(source)` | [`dynamic(source)`][wybthon.dynamic], called like a component |
| `<Portal mount>` | [`Portal(children, mount=...)`][wybthon.Portal] |
| `lazy(() => import(...))` | [`lazy(loader)`][wybthon.lazy] |
| `createContext(default)` | [`create_context(default)`][wybthon.create_context] |
| `<Ctx value>` | `Ctx(value, *children)`: the context object is the provider |
| `useContext(Ctx)` | [`use_context(Ctx)`][wybthon.use_context] |
| `interface CardProps` / `props: CardProps` | A [`Props`][wybthon.Props] subclass: `class CardProps(Props)` and `def Card(props: CardProps)` |
| `props.title` (getter) | `props.title` returns an accessor: place it in the tree or call `props.title()` in a scope |
| `ParentProps<T>` | [`ParentProps`][wybthon.ParentProps] |
| `merge(a, b)` | [`merge(a, b)`][wybthon.merge] |
| `omit(props, ...keys)` | [`omit(props, *keys)`][wybthon.omit] |
| `omit(props, predicate)` | `omit(props, lambda key: ...)` |
| `children(() => props.children)` | [`children(props.children)`][wybthon.children] |
| `children(...).toArray()` | `children(props.children).to_array()` |
| `createUniqueId()` | [`create_unique_id()`][wybthon.create_unique_id] |
| `renderToString(fn)` | [`render_to_string(view)`][wybthon.server.render_to_string] |
| `renderToStream(fn)` | [`render_to_stream(view)`][wybthon.server.render_to_stream]: iterate it for chunks |
| `await renderToStream(fn)` (replaces `renderToStringAsync`) | `await render_to_stream(view)` returns the complete HTML |
| `hydrate(fn, el)` | [`hydrate(view, container)`][wybthon.hydrate] |
| `isServer` | [`is_server()`][wybthon.is_server] |
| `isHydrating()` | [`is_hydrating()`][wybthon.is_hydrating] |
| `<NoHydration>` | [`NoHydration(*children)`][wybthon.NoHydration] |
| `<Hydration>` | [`Hydration(*children)`][wybthon.Hydration] (a passthrough; a `NoHydration` region stays static as a whole) |
| `getRequestEvent()` | [`get_request_event()`][wybthon.get_request_event] |
| `httpStatus(code)` | [`http_status(code)`][wybthon.http_status] |
| `httpHeader(name, value)` | [`http_header(name, value)`][wybthon.http_header] |
| `clientOnly(() => import(...))` | [`client_only(children, fallback=...)`][wybthon.client_only] |
| `createMemo(fn, { ssrSource })` | `create_memo(fn, ssr_source="server" \| "hybrid" \| "client")` |
| `ref={el => ...}` | `ref=Ref()`; read `ref.current.element` after `on_settled` |
| JSX | HTML helpers, holes, and t-strings (below) |

Solid 1.x primitives that 2.0 removed (`createResource`, `on`, `createComputed`, `createDeferred`, `createSelector`, `produce`, `createMutable`, `splitProps`, `mergeProps`, `Index`, path-based store writes, `useTransition`, `renderToStringAsync`) don't exist here either. The table above covers their 2.0 replacements.

## JSX becomes helpers and holes

```jsx
function Greeting(props) {
  return <p class="greeting">Hello, {props.name}{props.excited ? "!" : "."}</p>;
}
```

```python
from wybthon import Prop, Props, component, p, prop


class GreetingProps(Props):
    name: Prop[str]
    excited: Prop[bool] = prop(default=False)


@component
def Greeting(props: GreetingProps):
    return p("Hello, ", props.name, lambda: "!" if props.excited() else ".", class_="greeting")
```

- Children are positional arguments; attributes are keyword arguments. Names that collide with Python keywords or builtins get a trailing underscore (`class_`, `input_`, `main_`, `del_`), and `html_for` stands in for `for`. Item syntax reads like nesting: `div(class_="card")[h2("Title"), p("Body")]`.
- `{expr}` in JSX becomes a **hole**: any zero-argument callable placed in the tree. An accessor (`props.name`, or a signal getter) is already a callable, so it goes in directly; wrap other expressions in `lambda:`.
- Text with several reactive parts reads best as a [t-string](https://peps.python.org/pep-0750/): `p(t"Count: {count} (doubled: {doubled})")` is one binding that updates the whole string together, like a JSX text node with several `{}` holes.
- Attributes accept accessors, lambdas, and t-strings the same way: `class_=lambda: "on" if active() else ""`, `href=t"/users/{user_id}"`, `disabled=add.pending`.
- Event handlers are `on_click=handler`. A handler may take no arguments (`on_click=lambda: set_open(False)`) or receive a [`DomEvent`][wybthon.DomEvent] with `e.target`, `e.key`, `e.prevent_default()`, and friends.
- Tag helpers exist for every HTML element (from `wybthon`) and SVG element (from [`wybthon.svg`][wybthon.svg]). For custom elements, use [`h("my-element", {...}, *children)`][wybthon.h].

## Components and props

Solid types props with an interface (`props: CardProps`); Wybthon declares them on a [`Props`][wybthon.Props] class, and the component takes one parameter annotated with it. Pyright and mypy check every call against the class with no plugin.

```tsx
interface CardProps extends ParentProps {
  title: string;
  body?: string;
  onClose?: () => void;
}

function Card(props: CardProps) {
  return (
    <div class="card">
      <h2>{props.title}</h2>
      <p>{props.body ?? ""}</p>
      {props.children}
      <button onClick={() => props.onClose?.()}>Close</button>
    </div>
  );
}

<Card title="Hello" onClose={() => setOpen(false)}><p>Body</p></Card>
```

```python
from collections.abc import Callable

from wybthon import ParentProps, Prop, button, component, create_signal, div, h2, p, prop


class CardProps(ParentProps):
    title: Prop[str]
    body: Prop[str] = prop(default="")
    on_close: Callable[[], None] | None = None


@component
def Card(props: CardProps):
    def close():
        if props.on_close is not None:
            props.on_close()

    return div(
        h2(props.title),
        p(props.body),
        props.children,
        button("Close", on_click=close),
        class_="card",
    )


@component
def App():
    open_, set_open = create_signal(True)
    return Card(title="Hello", on_close=lambda: set_open(False))[p("Body")]
```

- A `Prop[T]` field is the counterpart of a getter on Solid's props proxy: reading `props.title` returns an accessor. Pass it straight into the tree to create a hole, or call it inside a memo, effect, or hole. The parent may pass a value, an accessor, or a zero-argument function.
- Fields annotated with anything else are plain data, returned exactly as the parent passed them. Declare callbacks this way; reading `props.on_close` never calls it.
- Optional props get defaults with `prop(default=...)`; plain fields use ordinary defaults.
- Assigning `value = props.title()` at the top of the body destructures and freezes, as in Solid; dev mode warns. Use `props.title.peek()` when you mean it.
- [`merge`][wybthon.merge] and [`omit`][wybthon.omit] match Solid 2.0's helpers and return mappings you can spread onto elements: `div(**omit(props, "title", "children"))`. There's no `**rest`; a component reads only what it declares.
- Children arrive as the `children` prop. Pass them with item syntax (`Card(title="Hi")[...]`) or the `children=` keyword.
- Every component accepts `key=`. A component with no props takes no parameters.

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

The split form is Solid 2.0's `createEffect(compute, apply)`: `compute` runs tracked, `apply` runs untracked with the value and previous value, and may return a cleanup. Effects run after the DOM commit; the first run happens on the flush after the component mounted. The single-function form `create_tracked_effect(fn)` also works.

Signal semantics that carry over:

- **Automatic batching.** All writes in one turn coalesce into one flush; there's no `batch()`.
- **Glitch-free propagation.** An effect that reads several memos derived from the same signal runs once per flush and never sees an inconsistent pair.
- **Lazy memos with equality short-circuit.** `create_memo` recomputes when read after a source changed and doesn't notify if the value is equal under `equals`.
- **Async-first.** An `async def` passed to `create_memo` is an async computation. Reading it before the first value raises [`NotReadyError`][wybthon.NotReadyError] (which `Loading` catches); later recomputes run as transitions that hold the dependent UI on the previous state until the new value lands.

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
from wybthon.router import current_path

Errored(
    lambda: Loading(lambda: Dashboard(), fallback=p("Loading...")),
    fallback=lambda err, reset: div(p(lambda: str(err())), button("Retry", on_click=reset)),
    reset_on=current_path,
)
```

`Loading` and `Errored` match their Solid 2.0 namesakes. The error fallback receives `(err, reset)`, where `err` is an accessor for the caught error, as in Solid 2.0; `reset_on` re-mounts when the given accessor changes. [`Reveal`][wybthon.Reveal] coordinates multiple boundaries like `SuspenseList`.

## Stores

```python
from wybthon import create_store, reconcile, snapshot

state, set_state = create_store({"count": 0, "items": []})


def update(s):
    s.count += 1
    s["items"].append({"id": 3, "title": "new"})


set_state(update)
set_state(reconcile({"count": 5, "items": fetched_items}, key="id"))
raw = snapshot(state["items"])
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

The transition model is Solid 2.0's too. A change that makes an async memo recompute holds the UI that depends on it until the new value lands, so a header reading `user_id` and a body reading `user` never disagree; `is_pending` reports the hold and `latest` reads ahead of it. An action's writes are staged into the same transaction and reveal together when it settles, while optimistic writes reveal now and revert on settle. `Loading(on=...)` names the inputs whose change should show the fallback again instead of holding, and `Errored` heals when the failing computation's inputs change.

## Server rendering

```python
import asyncio

from wybthon import Loading, NoHydration, RequestEvent, component, create_memo, div, footer, h1, http_status, p
from wybthon.server import render_to_stream, render_to_string


@component
def NotFound():
    http_status(404)
    return h1("Not found")


@component
def Page():
    async def load():
        await asyncio.sleep(0)
        return "Ada"

    name = create_memo(load)
    return div(
        Loading(lambda: p("Hello, ", name), fallback=p("Loading...")),
        NoHydration(footer("Static footer")),
    )


async def main():
    event = RequestEvent(url="/missing")
    html = render_to_string(NotFound(), event=event)
    assert event.response.status == 404

    html = await render_to_stream(Page(), url="/")  # complete HTML, data embedded
    async for chunk in render_to_stream(Page(), url="/"):  # out-of-order streaming
        print(chunk)


asyncio.run(main())
```

As in RC.14, awaiting [`render_to_stream`][wybthon.server.render_to_stream] replaces `renderToStringAsync`: it waits for every async memo the page reads and returns the complete HTML. Iterating it streams the shell first, then each `Loading` boundary as its data arrives. A stream is single use: iterate it or await it, once. [`http_status`][wybthon.http_status] and [`http_header`][wybthon.http_header] are tied to the scope that declared them, so a branch that's disposed before the response head is committed (an error boundary recovering, say) retracts its status. [`NoHydration`][wybthon.NoHydration] keeps a region as static server HTML that the browser adopts without mounting.

## What's intentionally different

- **Naming.** snake_case across the API; component names stay PascalCase; `_` suffix on tags that collide with Python keywords or builtins.
- **A virtual DOM under the reactive graph.** Solid compiles JSX to direct DOM operations. Wybthon builds a lightweight VNode tree and a reconciler applies changes in batches through a small JS kernel. You still get fine-grained holes as the unit of update. Instead of compiling JSX ahead of time, Wybthon compiles each repeated subtree shape at run time into a mount function that clones a pre-parsed template in one kernel command.
- **Staged writes.** After `set_x(1)`, `x()` returns the old value until the flush (end of the handler, or `flush()`). Solid 2.0 leans the same way; Wybthon makes it strict. Use functional updates (`set_x(lambda v: v + 1)`) to compose writes, and `create_signal`'s returned setter gives back the staged value if you need it.
- **Writes are forbidden inside tracking scopes.** Writing a signal from a memo body, a hole, or a single-function effect raises `WriteInScopeError` in dev mode. Write from handlers, actions, `on_settled`, or the `apply` stage.
- **Equality.** The default `equals` is Python `==` with an identity fast path, not `===`. Pass `equals=lambda a, b: a is b` for identity-only, `equals=False` to always notify.
- **`.peek()`.** Every accessor has `.peek()`, a one-read `untrack`.
- **`on_settled` instead of `onMount`.** The name reflects when it runs: after the flush that mounted the component committed to the DOM. It may return a cleanup.
- **Python 3.14.** Template strings (PEP 750) stand in for JSX text holes, and the framework's own generics (`Accessor[T]`, `Prop[T]`) are meant to be written in your code.
- **JS interop through Pyodide.** `from js import fetch`, `pyodide.ffi.create_proxy` for callbacks, `.to_py()` for JS objects. See the [Pyodide guide](pyodide.md).

## What carries over directly

- The mental model: components run once, reactivity is fine-grained, ownership handles cleanup.
- The 2.0 async story: async memos, transitions, `Loading`, `Reveal`, `is_pending`, `latest`, `resolve`, `refresh`, actions as transactions, optimistic state, `affects`, `until`, error boundary healing.
- Draft-first stores, `reconcile`, projections.
- Flow components, boundaries, context, lazy, portals.

## Next steps

- Read [Mental model](../concepts/mental-model.md) to see the formal definitions of holes and scopes.
- Explore [Authoring patterns](authoring-patterns.md); most should look familiar.
- Browse the [API reference](../api/wybthon.md) for the full set of primitives.
