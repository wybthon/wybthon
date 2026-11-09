# Migrating from Solid

Wybthon is SolidJS for Python, and it tracks **SolidJS 2.0** semantics: async-first reactivity, automatic batching, actions and optimistic state, draft-first stores, and the `For` plus `Repeat` flow components. Nearly every primitive has a direct equivalent, and the mental model is identical: components run once, signals drive fine-grained updates, the ownership tree manages cleanup, and a compiler turns the dynamic expressions in your markup into getters.

Solid 2.0 hasn't had a stable release yet. Release candidate 21 (RC.21) is the latest, and it's the version Wybthon targets.

The differences are mostly surface: Python instead of JavaScript, t-string templates instead of JSX, function parameters instead of a props interface, snake_case names, and a small number of deliberate semantic choices listed at the end.

## API mapping

The table follows **Solid 2.0 RC.21**.

| SolidJS 2.0 | Wybthon |
| --- | --- |
| `createSignal(initial)` | [`create_signal(initial)`][wybthon.create_signal] |
| `createSignal(() => derived)` (function form) | `create_signal(lambda: derived())` |
| `createMemo(fn, { equals })` | [`create_memo(fn, equals=...)`][wybthon.create_memo] |
| `createMemo(async () => ...)` | `create_memo(async_fn)`: an `async def` body makes an async memo |
| `createDeferred(fn)` | [`create_deferred(fn)`][wybthon.create_deferred]: an async memo whose refetches never hold the rest of the UI |
| `isEqual(a, b)` | [`is_equal(a, b)`][wybthon.is_equal]: the default equality |
| `createEffect(compute, apply)` | [`create_effect(compute, apply)`][wybthon.create_effect] |
| `createEffect(fn)` | `create_tracked_effect(fn)` (single function, tracked) |
| `createRenderEffect(compute, apply)` | [`create_render_effect(compute, apply)`][wybthon.create_render_effect] |
| `createReaction(effect)` | [`create_reaction(effect)`][wybthon.reactivity.create_reaction] returns `track(fn)` |
| `onMount(fn)` | [`on_settled(fn)`][wybthon.on_settled] |
| `onFlush(fn)` | [`on_flush(fn)`][wybthon.on_flush] |
| `onCleanup(fn)` | [`on_cleanup(fn)`][wybthon.on_cleanup] |
| `createRoot(dispose => ...)` | [`create_root(lambda dispose: ...)`][wybthon.create_root] |
| `getOwner()` / `runWithOwner(owner, fn)` | [`get_owner()`][wybthon.get_owner] / [`run_with_owner(owner, fn)`][wybthon.run_with_owner] |
| `isDisposed(owner)` | [`is_disposed(owner)`][wybthon.is_disposed] (Solid 2.0 RC.21 removed `createOwner`; use `create_root` and `run_with_owner`) |
| `getObserver()` | [`get_observer()`][wybthon.reactivity.get_observer] |
| `untrack(fn)` | [`untrack(fn)`][wybthon.untrack], or `accessor.peek()` for a single read |
| `batch(fn)` | Nothing to call; every write batches until the next flush. [`flush()`][wybthon.flush] settles synchronously. |
| `flush()` / `flush(fn)` | [`flush()`][wybthon.flush] / `flush(fn)` |
| `createSignal(v, { ownedWrite: true })` | `create_signal(v, owned_write=True)` |
| `isPending(fn)` | [`is_pending(fn)`][wybthon.is_pending] |
| `latest(fn)` | [`latest(fn)`][wybthon.latest] |
| `resolve(fn)` | [`await resolve(fn)`][wybthon.resolve] |
| `from(source)` | [`from_source(source)`][wybthon.from_source] (`from` is a Python keyword) |
| `refresh(memo)` | [`await refresh(memo)`][wybthon.refresh] |
| `action(fn)` | [`action(fn)`][wybthon.action], usable as `@action` |
| `createOptimistic(source)` | [`create_optimistic(source)`][wybthon.create_optimistic] |
| `createOptimisticStore(source)` | [`create_optimistic_store(source)`][wybthon.create_optimistic_store] |
| `affects(...)` | [`affects(...)`][wybthon.affects] |
| `until(pred)` | [`await until(pred)`][wybthon.until] |
| `TimeoutError` | `until(..., timeout=...)` raises the built-in `TimeoutError` |
| `createMemo(fn, { loadingValue })` | `create_memo(fn, loading_value=...)` |
| `NotReadyError` | [`NotReadyError`][wybthon.NotReadyError] |
| `createStore(initial)` (draft setter) | [`create_store(initial)`][wybthon.create_store], where `initial` is a dataclass instance, a dict, or a list |
| `reconcile(value, key)` | [`reconcile(value, key="id")`][wybthon.reconcile]; `key` may be a string, a function, or `None` |
| `createProjection(fn, initial)` | [`create_projection(fn, initial)`][wybthon.create_projection] |
| `createSelector(source)` (removed in 2.0) | A projection: `create_projection(lambda: {} if sel() is None else {sel(): True})`, then `is_selected.get(key)` |
| `unwrap(store)` | [`snapshot(store)`][wybthon.snapshot] |
| `mapArray(list, fn, { fallback })` | [`map_array(list, fn, fallback=...)`][wybthon.reactivity.map_array] |
| `indexArray(list, fn)` | `map_array(list, fn, keyed=False)` |
| `repeat(count, fn, { from, fallback })` | [`repeat(count, fn, start=..., fallback=...)`][wybthon.reactivity.repeat] |
| `<Loading fallback>` (was `Suspense`) | [`Loading(children, fallback=...)`][wybthon.Loading] |
| `<Reveal order collapsed>` (was `SuspenseList`) | [`Reveal(children, order=..., collapsed=...)`][wybthon.Reveal] |
| `<Errored fallback={(err, reset) => ...}>` | [`Errored(children, fallback=lambda err, reset: ...)`][wybthon.Errored]; `err` is an accessor, so call `err()` |
| `<Show when fallback>` | [`{Show(when, children, fallback=...)}`][wybthon.Show] |
| `<For each>` | [`{For(each, children)}`][wybthon.For] (keyed by identity) |
| `<For each keyed={fn}>` | `{For(each, children, keyed=lambda item: ...)}` |
| `<For each keyed={false}>` (was `Index`) | `{For(each, children, keyed=False)}` |
| `<Repeat count>` | [`{Repeat(count, children)}`][wybthon.Repeat] |
| `<Switch>` / `<Match when>` | [`{Switch(...)}`][wybthon.Switch] / [`Match(when, children)`][wybthon.Match] |
| `dynamic(source)` | [`dynamic(source)`][wybthon.dynamic], called like a component |
| `<Portal mount>` | [`Portal(children, mount=...)`][wybthon.Portal] |
| `lazy(() => import(...))` | [`lazy(loader)`][wybthon.lazy] |
| `lazyModule(() => import(...))` | [`lazy_module(loader)`][wybthon.lazy_module]: a cached async import with `preload()` and `peek()` |
| `createContext(default)` | [`create_context(default)`][wybthon.create_context] |
| `<Ctx value>` | `Ctx(value, *children)`: the context object is the provider |
| `useContext(Ctx)` | [`use_context(Ctx)`][wybthon.use_context] |
| `interface CardProps` / `props: CardProps` | Parameters: `def Card(title: str, body: str = "")`; each parameter is a prop, and its annotation is the prop's type |
| `props.title` (getter) | `title`: reading the parameter returns the value, tracked |
| `isStatic(props, key)` | [`is_static(title)`][wybthon.is_static]: pass the parameter itself |
| `ParentProps<T>` | A `children: Children = None` parameter ([`Children`][wybthon.Children]) |
| `merge(a, b)` | [`merge(a, b)`][wybthon.merge], over dicts, `**rest` views, and other views |
| `const rest = omit(props, "label")` (the rest pattern; `splitProps` in 1.x) | A `**rest` parameter: `def Button(label: str, **attrs: Any)` collects the props `Button` doesn't declare, ready to spread with `<button {attrs}>` |
| `omit(props, ...keys)` | [`omit(attrs, *keys)`][wybthon.omit], on a `**rest` view, another view, or a dict |
| `omit(props, predicate)` | `omit(attrs, lambda key: ...)` |
| `children(() => props.children)` | [`resolve_children(lambda: children)`][wybthon.resolve_children] |
| `children(...).toArray()` | `resolve_children(lambda: children).to_array()` |
| `flatten(children)` | [`flatten(children)`][wybthon.flatten]: the unmemoized form of `children` |
| `createUniqueId()` | [`create_unique_id()`][wybthon.create_unique_id] |
| `renderToString(fn)` | [`render_to_string(view)`][wybthon.server.render_to_string] |
| `renderToStream(fn)` | [`render_to_stream(view)`][wybthon.server.render_to_stream]: iterate it for chunks |
| `await renderToStream(fn)` (replaces `renderToStringAsync`) | `await render_to_stream(view)` returns the complete HTML |
| `hydrate(fn, el)` | [`hydrate(view, container)`][wybthon.hydrate] |
| `isServer` | [`is_server()`][wybthon.is_server] |
| `isHydrating()` | [`is_hydrating()`][wybthon.is_hydrating] |
| `onHydrationEnd(fn)` | [`on_hydration_end(fn)`][wybthon.on_hydration_end] |
| `<NoHydration>` | [`NoHydration(*children)`][wybthon.NoHydration] |
| `<Hydration>` | [`Hydration(*children)`][wybthon.Hydration] (a passthrough; a `NoHydration` region stays static as a whole) |
| `getRequestEvent()` | [`get_request_event()`][wybthon.get_request_event] |
| `httpStatus(code)` | [`http_status(code)`][wybthon.http_status] |
| `httpHeader(name, value)` | [`http_header(name, value)`][wybthon.http_header] |
| `clientOnly(() => import(...))` | [`client_only(children, fallback=...)`][wybthon.client_only] |
| `createMemo(fn, { ssrSource })` | `create_memo(fn, ssr_source="server" \| "hybrid" \| "client")` |
| `ref={el => ...}` | A callback ref: `ref={remember}` (or `ref={(lambda el: ...)}`), which receives an [`Element`][wybthon.Element] |
| `let el; <input ref={el} />` | `ref = Ref()` and `ref={ref}`; read `ref.current.element` in `on_settled` |
| JSX, or `html` from `solid-js/html` | [`html(t"...")`][wybthon.html] templates, compiled like JSX (below) |
| `{expr}` | `{expr}`: the compiler makes it a getter when it contains a call, attribute access, or subscript |
| `<Card title={user().name}>...</Card>` | `<{Card} title={user().name}>...</{Card}>`, or `{Card(title=user().name, children=...)}` |
| `<div {...attrs}>` | `<div {attrs}>` |
| `h(tag, props, ...children)` | [`h(tag, props, *children)`][wybthon.vnode.h] |
| `"use server"` (`@solidjs/web/server-functions`) | [`@server_function`][wybthon.server_function] on a module-level `async def` |
| `GET(fn)` | `@server_function(method="GET")` |
| `redirect`, `reload`, `respond` (`@solidjs/web`) | [`redirect`][wybthon.redirect], [`reload`][wybthon.reload], [`respond`][wybthon.respond]: raise or return them |
| `getRequestEvent()` in a server function | [`get_request_event()`][wybthon.get_request_event]; set cookies with [`set_cookie`][wybthon.set_cookie] |

Solid Router 2.0 (`@solidjs/router` 2.0, the `next` line) maps to `wybthon.router`:

| Solid Router 2.0 | Wybthon |
| --- | --- |
| `const Router = createRouter({ routes, base, preloadLinks })` | `router = create_router(routes, base=..., preload_links=True)` ([`create_router`][wybthon.router.create_router]) |
| `<Router>{props => <Layout>{props.children}</Layout>}</Router>` | `router(root=Layout)`, where `Layout` declares a `children` parameter |
| `{ path, component, children, preload }` | [`Route(path, component, children=[...], preload=...)`][wybthon.router.Route] |
| A route component's `props.params`, `props.data`, `props.children` | Parameters the route component declares: `params: dict[str, str]`, `search: SearchParams`, `data: Any`, `children: Children`; the router passes only the ones it declares |
| `fileRoutes(...)` from `@solidjs/router/fs` | [`file_routes("app.routes")`][wybthon.router.file_routes] |
| `<a href>` (router-handled) | `<a href>`, unchanged |
| `useLinkState(href)` | [`use_link_state(href)`][wybthon.router.use_link_state] |
| `useParams()`, `useSearchParams()`, `useLocation()` | [`use_params()`][wybthon.router.use_params], [`use_search_params()`][wybthon.router.use_search_params], [`use_location()`][wybthon.router.use_location] |
| `useRouteMatches()` | [`use_route_matches()`][wybthon.router.use_route_matches] |
| `usePreloadRoute()` | [`preload_route(href)`][wybthon.router.preload_route] |
| `useNavigate()` | [`navigate(path)`][wybthon.router.navigate] |
| `query(fn, "key")` | [`query(fn, "key")`][wybthon.router.query], or `@query` / `@query("key")` |
| `revalidate(key)` | [`revalidate(key)`][wybthon.router.revalidate]; a `Query` works as its key |
| `formAction(fn)`, `.with(...)` | [`form_action(fn)`][wybthon.router.form_action], `.bind(...)` (`with` is a Python keyword) |
| `.onSubmit(fn)`, `.onSettled(fn)` | `.on_submit(fn)`, `.on_settled(fn)` |
| `useSubmissions(action)` | [`use_submissions(action)`][wybthon.router.use_submissions] |
| Start mode (`solid({ start: true })`) | `server = true` in `wybthon.toml`; `wyb dev`, `wyb serve`, or [`wybthon.asgi`][wybthon.asgi] |

Solid 1.x primitives that 2.0 removed (`createResource`, `on`, `createComputed`, `createSelector`, `produce`, `createMutable`, `splitProps`, `mergeProps`, `Index`, path-based store writes, `useTransition`, `renderToStringAsync`) don't exist here either. The table above covers their 2.0 replacements. Solid 2.0's `createDeferred` isn't 1.x's idle-time deferral: it's the async memo in the table, and that's what `create_deferred` mirrors.

`createAsync` was never part of Solid 2.0's core API: it came from `@solidjs/router` 0.x and was removed in router 2.0. In Solid 2.0 you read async data with `createMemo`, and that's what `create_memo` with an `async def` mirrors.

## JSX becomes templates

```jsx
function Greeting(props) {
  return <p class="greeting">Hello, {props.name}{props.excited ? "!" : "."}</p>;
}
```

```python
from wybthon import component, html


@component
def Greeting(name: str, excited: bool = False):
    return html(t'<p class="greeting">Hello, {name}{"!" if excited else "."}</p>')
```

- [`html`][wybthon.html] takes a Python 3.14 [template string](https://peps.python.org/pep-0750/), and Wybthon's [compiler](../concepts/compiler.md) does the two jobs Solid's JSX compiler does. It turns each literal's static markup into a native `<template>` that the kernel clones for every instance, and it turns every dynamic expression into a getter. It runs when `wyb build` and `wyb dev` build your app, in an import hook that `import wybthon` installs, under pytest, and for scripts run with `wyb run script.py`. See [Templates](../concepts/templates.md).
- The rule is Solid's: an interpolation that contains a call, an attribute access, or a subscript is **dynamic**, so `{user.name}`, `{count() * 2}`, `{row["label"]}`, and `class={"on" if active() else ""}` become getters, and each updates only its own text node or attribute. A name, a constant, or a lambda is a value, with one exception: a component's parameter is a prop, so `{name}` in `Greeting` above is dynamic, like `{props.name}` in JSX. A signal placed directly (`{count}`) is still bound reactively, so `{count}` and `{count()}` both work.
- Event handlers, refs, spreads, and nested `html(t"...")` templates are never wrapped. Prefer a named handler (`onclick={increment}`); Python forbids a bare `lambda` in an interpolation, so an inline one needs parentheses: `onclick={(lambda: set_open(False))}`.
- A call in a child position is decided when the template is created. A component (`{Card(title=user().name)}`, `{Show(...)}`, `{For(...)}`) is built with a getter for each dynamic argument, exactly like `<Card title={user().name} />`. Any other call (`{badge(user())}`, `{str(total())}`) becomes one reactive hole, as a function call in JSX does.
- Attributes are HTML names (`class`, `for`, `aria-label`) and take interpolations the same way: `class={row_class(id)}`, `href="/users/{user_id()}"` (one binding for the whole value), `disabled={add.pending()}`.
- Event handlers are `onclick={handler}`, the HTML name, where Solid 2.0 binds `onClick`; `on:click` attaches a native listener to the element instead of a delegated one. Other spellings (`onClick`, `on_click`) are compile errors that name the one to use. A handler may take no arguments or receive a [`DomEvent`][wybthon.DomEvent] with `e.target`, `e.key`, `e.prevent_default()`, and friends.
- A component tag is written `<{Card} title={user().name}>...</{Card}>` (like `<${Card}>` in Solid's `html`), or self-closed as `<{Card} />`. Attributes become keyword props (`onclick` becomes `on_click`, as a callback parameter spells it) and the content becomes `children`. Type checkers can't see a tag's attributes, so dev mode checks its props at run time; the call form (`{Card(title=user().name)}`) is checked statically, and the compiler still passes getters.
- `Show`, `Loading`, `Errored`, and context providers work as calls in an interpolation (`{Show(ready(), panel)}`) or with the tag form (`<{Show} when={ready()}>...</{Show}>`), which calls each the way its signature takes children.
- Markup the browser's parser would rewrite is an error instead of a silent change: put `<tr>` in a `<tbody>`, and don't nest a `<div>` in a `<p>`. The compiler reports it as a `SyntaxError` with the file and line.
- A template that reaches `html()` without being compiled (a REPL, `exec`) has already evaluated its dynamic expressions once, so dev mode raises [`TemplateError`][wybthon.TemplateError] instead of rendering markup that would never update.
- [`h(tag, props, *children)`][wybthon.vnode.h] is the programmatic layer, the counterpart of Solid's `h`, for markup built by code. Its props take Python names (`class_`, `html_for`, `on_click`) or HTML names. SVG works in a template.

## Components and props

Solid types props with an interface (`props: CardProps`); in Wybthon, a component's parameters are its props. Each parameter is a prop, its annotation is the prop's type, and its default makes it optional. Pyright and mypy check every call against the function's own signature with no plugin, and Wybthon's compiler makes every read of a parameter a tracked read of the parent's current value, so the parameters behave like Solid's props object without the `props.` prefix.

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

<Card title={user().name} onClose={() => setOpen(false)}><p>Body</p></Card>
```

```python
from collections.abc import Callable

from wybthon import Children, component, create_signal, html


@component
def Card(title: str, body: str = "", on_close: Callable[[], None] | None = None, children: Children = None):
    def close():
        if on_close is not None:
            on_close()

    return html(t"""
      <div class="card">
        <h2>{title}</h2>
        <p>{body}</p>
        {children}
        <button onclick={close}>Close</button>
      </div>
    """)


@component
def App():
    user, set_user = create_signal({"name": "Ada"})
    open_, set_open = create_signal(True)

    def close():
        set_open(False)

    return html(t"<{Card} title={user()['name']} on_close={close}><p>Body</p></{Card}>")
```

- Props work as they do in Solid: reading `title` returns the value and tracks it, like reading a getter on Solid's props object. In markup, `{title}` is dynamic, so the compiler makes it a getter and the text updates when the parent's value changes. `{body or "No details."}` is one expression and one binding. A handler that reads a parameter gets the latest value when it runs.
- The parent may pass a value, a compiler getter (what `title={user()["name"]}` becomes), or an accessor such as a signal. Getters and accessors are unwrapped when the parameter is read, unless the parameter is annotated as callable (`Callable[...]` or `Accessor[...]`, alone or in a union with `None`): then the value is returned exactly as passed, which is how callbacks work.
- Passing a prop through stays reactive: `<{Child} title={title}>` hands the child a getter, as in Solid.
- Optional props take ordinary defaults (`body: str = ""`). Use [`prop(default_factory=list)`][wybthon.prop] for a mutable default; the factory runs once per component instance.
- Assigning `label = title.upper()` at the top of the body reads once and freezes, as destructuring does in Solid; dev mode warns when the value is reactive. Use `untrack(lambda: initial)` when a one-time read is what you mean, as in `create_signal(untrack(lambda: initial))`.
- Parameters are read-only, like Solid's props object. Assigning to one is a compile-time `SyntaxError` that tells you to use a new name.
- [`is_static(title)`][wybthon.is_static] says whether the parent passed a plain value, as Solid 2.0's `isStatic` does. Pass the parameter itself; the compiler turns it into a question about the prop.
- A `**rest` parameter (any name, such as `**attrs: Any`) collects the props the component doesn't declare, as a reactive, read-only view. It's the rest pattern that Solid 2.0 writes with `omit(props, ...)` (and 1.x with `splitProps`): `def Button(label: str, **attrs: Any)`, then `<button {attrs}>{label}</button>`.
- [`merge`][wybthon.merge] and [`omit`][wybthon.omit] match Solid 2.0's helpers and work on dicts, `**rest` views, and other views: `omit(attrs, "title")`, `merge({"type": "button"}, attrs)`. A view reads like props (`view.title` is the tracked value), and you can spread it onto an element.
- Children arrive in the `children` parameter. Pass them as nested markup in the tag form, with the `children=` keyword, or with item syntax in Python code (`Card(title="Hi")[...]`). Inside a template, `{Card(...)[...]}` is a subscript rather than a call, so it becomes one reactive hole instead of a component built with getters.
- Positional arguments bind to parameters as in any Python call, so `Greeting("Ada")` is `Greeting(name="Ada")`. They're never children, and a component can't take `*args`.
- A component with no props takes no parameters. Components don't take `key=`; for a keyed remount, use a keyed `Show` (below).

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
from wybthon import For, Match, Show, Switch, create_signal, create_store, html

user, set_user = create_signal(None)
status, set_status = create_signal("loading")
store, set_store = create_store({"todos": [{"id": 1, "title": "Write docs"}]})


def greeting(u):
    return html(t"<p>Hello, {u()['name']}</p>")


def todo_row(todo, i):
    return html(t"<li>{todo()['title']}</li>")


html(t"""
  <main>
    {Show(user, greeting, fallback=html(t"<p>Sign in</p>"))}
    <ul>{For(store["todos"], todo_row, keyed=lambda t: t["id"])}</ul>
    {
    Switch(
        Match(status() == "loading", html(t"<p>Loading...</p>")),
        Match(status() == "ready", html(t"<p>Ready</p>")),
        fallback=html(t"<p>Unknown</p>"),
    )
}
  </main>
""")
```

These are calls in a child position, so the compiler builds them like JSX components: `status() == "loading"` and `store["todos"]` arrive as getters, and `Match` inside `Switch` is prepared the same way. `Show` passes the truthy value to a one-argument callback as an accessor, like Solid's `<Show>` with a function child; with `keyed=True` it passes the value itself. `For` mirrors Solid's unified `For`: with `keyed=True` (the default) rows match by identity and the callback receives `(item, index_accessor)`; with `keyed=False` it receives `(item_accessor, index)`; with a key function it receives `(item_accessor, index_accessor)`. Type checkers infer these from the call (see [Typing](typing.md#control-flow)). In a template, `{For(todos(), row)}` passes a getter; in Python code, pass the accessor (`For(todos, row)`) or a store list, because a plain list renders once. `Repeat(count, lambda i: ...)` matches Solid 2.0's `Repeat`.

Branches are lazy, as JSX children are in Solid. When the content or fallback of `Show`, `Match`, `Switch`, `Loading`, `Errored`, or `client_only` is written as markup (`html(t"...")`) or a component call (a call whose callee name is capitalized), the compiler makes it a zero-argument function, so `<p>Sign in</p>` above is built only while that branch shows. A name, a lambda, or a lowercase call is passed as written, so markup you build ahead of time and pass by name is built eagerly.

A keyed `Show` is also how you remount a component when a value changes, since components don't take `key=`. Show it keyed on that value: `{Show(doc_id(), lambda id: DocumentView(doc_id=id), keyed=True)}`.

These are native regions, not wrapper components: `Show` and `Switch` are one branch computation each, and when a hole re-renders a tree containing one, the new condition or source is pushed into the mounted region instead of remounting it.

## Boundaries

```python
from wybthon import Errored, Loading, html
from wybthon.router import url


def failed(err, reset):
    return html(t"<div><p>{str(err())}</p><button onclick={reset}>Retry</button></div>")


Errored(
    Loading(Dashboard(), fallback=html(t"<p>Loading...</p>")),
    fallback=failed,
    reset_on=url,
)
```

`Loading` and `Errored` match their Solid 2.0 namesakes. The error fallback receives `(err, reset)`, where `err` is an accessor for the caught error, as in Solid 2.0; `reset_on` re-mounts when the given accessor changes. [`Reveal`][wybthon.Reveal] coordinates multiple boundaries like `SuspenseList`.

## Stores

```python
from dataclasses import dataclass, field

from wybthon import create_store, reconcile, snapshot


@dataclass
class Item:
    id: int
    title: str


@dataclass
class State:
    count: int = 0
    items: list[Item] = field(default_factory=list)


state, set_state = create_store(State())


def update(draft: State) -> None:
    draft.count += 1
    draft.items.append(Item(3, "new"))


set_state(update)
set_state(lambda draft: draft.items.clear())
set_state(reconcile(State(count=5, items=fetched_items), key="id"))
raw = snapshot(state.items)
```

Solid's `createStore(obj)` becomes `create_store(State(...))` with a dataclass instance. Its fields read as tracked attributes, like a Solid store proxy: `state.items[0].title` subscribes to that one field, and the dataclass's methods and properties work through the store. A dict store is read with subscripts instead (`state["items"]`) and has no attribute access, which suits JSON-like data and maps keyed by id.

Setters are draft-first, as in Solid 2.0: `setStore(draft => ...)` becomes `set_state(lambda draft: ...)` for a single expression, or a `def` like `update` above, since a Python lambda can't assign. A dataclass draft is edited like the dataclass (`draft.items[0].title = "renamed"`); a dict draft takes subscripts (`draft["count"] += 1`). Reads are tracked per field, only fields that changed notify, and `reconcile` preserves identity by key so `For` rows keep their DOM. [`create_projection`][wybthon.create_projection] and [`create_optimistic_store`][wybthon.create_optimistic_store] match their Solid 2.0 namesakes.

In Solid, a store created from an object of type `T` is typed as `T`. Wybthon does the same: `state` is typed as `State`, and the setter accepts a `Callable[[State], object]`, so pyright and mypy check store reads and draft edits with no plugin (see [Typing](typing.md#stores)).

Where you'd use a shallow store in Solid 2.0, pass `shallow=True`: `create_store(initial, shallow=True)` makes only the top level reactive. Nested values are stored and returned as plain data, so you change one by replacing it. See [Stores](../concepts/stores.md#shallow-stores).

## Context

```python
from wybthon import component, create_context, create_signal, html, use_context

Theme = create_context("light")


@component
def Root():
    theme, set_theme = create_signal("dark")
    return Theme(theme, Page())


@component
def Page():
    theme = use_context(Theme)
    return html(t"<p>Theme: {theme()}</p>")
```

There's no `.Provider`: calling the `Context` object with a value and children returns the provider node. `use_context` returns the value exactly as provided, so an accessor stays an accessor.

## Async, actions, and optimistic state

```python
from js import fetch

from wybthon import Loading, action, create_memo, create_optimistic, html, is_pending, refresh


async def fetch_user():
    resp = await fetch("/api/user")
    return (await resp.json()).to_py()


user = create_memo(fetch_user)

Loading(
    html(t"<p>{user()['name']}<span>{' (refreshing)' if is_pending(user) else ''}</span></p>"),
    fallback=html(t"<p>Loading...</p>"),
)

shown, set_shown = create_optimistic(likes)


@action
async def like():
    set_shown(lambda n: n + 1)
    await post_like()
    await refresh(likes)
```

Everything here has the same name and shape as Solid 2.0, with `await` in place of promise chaining. `like.pending()` is tracked, so it works directly as `disabled={like.pending()}`.

The transition model is Solid 2.0's too. A change that makes an async memo recompute holds the UI that depends on it until the new value lands, so a header reading `user_id` and a body reading `user` never disagree; `is_pending` reports the hold and `latest` reads ahead of it. An action's writes are staged into the same transaction and reveal together when it settles, while optimistic writes reveal now and revert on settle. `Loading(on=...)` names the inputs whose change should show the fallback again instead of holding, and `Errored` heals when the failing computation's inputs change.

## Server rendering

```python
import asyncio

from wybthon import Loading, NoHydration, RequestEvent, component, create_memo, html, http_status
from wybthon.server import render_to_stream, render_to_string


@component
def NotFound():
    http_status(404)
    return html(t"<h1>Not found</h1>")


@component
def Page():
    async def load():
        await asyncio.sleep(0)
        return "Ada"

    name = create_memo(load)
    greeting = Loading(html(t"<p>Hello, {name()}</p>"), fallback=html(t"<p>Loading...</p>"))
    footer = NoHydration(html(t"<footer>Static footer</footer>"))
    return html(t"<div>{greeting}{footer}</div>")


async def main():
    event = RequestEvent(url="/missing")
    markup = render_to_string(NotFound(), event=event)
    assert event.response.status == 404

    markup = await render_to_stream(Page(), url="/")  # complete HTML, data embedded
    async for chunk in render_to_stream(Page(), url="/"):  # out-of-order streaming
        print(chunk)


asyncio.run(main())
```

As in Solid 2.0, awaiting [`render_to_stream`][wybthon.server.render_to_stream] replaces `renderToStringAsync`: it waits for every async memo the page reads and returns the complete HTML. Iterating it streams the shell first, then each `Loading` boundary as its data arrives. A stream is single use: iterate it or await it, once. [`http_status`][wybthon.http_status] and [`http_header`][wybthon.http_header] are tied to the scope that declared them, so a branch that's disposed before the response head is committed (an error boundary recovering, say) retracts its status. [`NoHydration`][wybthon.NoHydration] keeps a region as static server HTML that the browser adopts without mounting.

## Server functions and the router's data layer

Solid 2.0 made `"use server"` part of core, and Router 2.0 builds `query` and `formAction` on it. Wybthon does the same with Python on both ends: see [Full-stack apps](../concepts/full-stack.md). The differences:

- **Arguments are validated.** The server rebuilds each argument from the function's annotations and rejects anything else, so annotate every parameter. Dataclasses, enums, dates, `Decimal`, and the rest cross as themselves.
- **No typed paths.** Router 2.0's `paths` proxy is a TypeScript feature; write hrefs as strings. Without it, a full path never gets the router's `base` added, as in Router 2.0.
- **No single-flight mutations or live queries yet.** A mutation's response carries its revalidation keys, and the browser refetches the queries they name; it doesn't carry the refreshed data in the same round trip. `liveQuery` and server components aren't implemented.
- **Errors are hidden in production.** An unexpected exception's message is sent only in development; raise `ServerError(message, type_name)` for messages meant for the page.

## What's intentionally different

- **Naming.** snake_case across the API; component names stay PascalCase.
- **Component calls are recognized at run time.** In JSX, `<Card />` and `badge()` look different; in a template, `{Card(title=...)}` and `{badge(...)}` are both calls. The compiler checks the callee when the template is created: a component gets getters for its props, and anything else becomes one reactive hole. A naming convention can't tell `Card(...)` from `Decimal(...)`, so Wybthon doesn't use one.
- **Destructuring is safe.** In Solid, `const { title } = props` reads once and loses reactivity, so you keep `props.` everywhere. A Wybthon component's parameters are the props themselves, not copies: a read in markup, a handler, a memo, an effect, or a nested function is tracked and returns the current value. Only a read at the top level of the body (`label = title.upper()`) is a one-time read, as destructuring is in Solid, and dev mode warns when the value was reactive.
- **Callable props are declared.** Solid's props getters return whatever the parent passed. Wybthon unwraps accessors the parent passes, unless the parameter's annotation is callable (`Callable[...]` or `Accessor[...]`), so a callback or an accessor you mean to keep must be annotated as one.
- **Components take no `key`.** As in Solid, a component call has no `key` prop. Use a keyed `Show` to remount on a value, and `For` for lists. The low-level `h(tag, {"key": ...})` still keys any node.
- **A virtual DOM under the reactive graph.** Solid compiles JSX to direct DOM operations. Wybthon's compiler also emits each template's parse tree and mount code ahead of time, but changes are applied in batches through a small JS kernel, so every update crosses from Python to JavaScript once. You still get fine-grained holes as the unit of update, and each template instance mounts with one native clone.
- **Callback refs receive a wrapper.** A function ref gets an [`Element`][wybthon.Element]; its `.element` is the raw DOM node.
- **Staged writes.** After `set_x(1)`, `x()` returns the old value until the flush (end of the handler, or `flush()`). Solid 2.0 leans the same way; Wybthon makes it strict. Use functional updates (`set_x(lambda v: v + 1)`) to compose writes, and `create_signal`'s returned setter gives back the staged value if you need it.
- **Writes are forbidden inside tracking scopes.** Writing a signal from a memo body, a hole, or a single-function effect raises `WriteInScopeError` in dev mode. Write from handlers, actions, `on_settled`, or the `apply` stage.
- **Equality.** The default `equals` ([`is_equal`][wybthon.is_equal]) is Python `==` with an identity fast path, not `===`. Pass `equals=lambda a, b: a is b` for identity-only, `equals=False` to always notify.
- **`.peek()`.** Every accessor has `.peek()`, a one-read `untrack`.
- **`on_settled` instead of `onMount`.** The name reflects when it runs: after the flush that mounted the component committed to the DOM. It may return a cleanup.
- **Python 3.14.** Template strings (PEP 750) stand in for JSX, and the framework's own generics (`Accessor[T]`, `Memo[T]`) are meant to be written in your code.
- **JS interop through Pyodide.** `from js import fetch`, `pyodide.ffi.create_proxy` for callbacks, `.to_py()` for JS objects. See the [Pyodide guide](pyodide.md).

## What carries over directly

- The mental model: components run once, reactivity is fine-grained, ownership handles cleanup.
- The compiler's contract: calls and member accesses in markup become getters, and props are values read through getters.
- The 2.0 async story: async memos, deferred memos, transitions, `Loading`, `Reveal`, `is_pending`, `latest`, `resolve`, `refresh`, actions as transactions, optimistic state, `affects`, `until`, error boundary healing.
- Draft-first stores, `reconcile`, projections.
- Flow components, boundaries, context, lazy components and modules, portals.

## Next steps

- Read [Mental model](../concepts/mental-model.md) to see the formal definitions of holes and scopes, and [The compiler](../concepts/compiler.md) for exactly what it rewrites.
- Explore [Authoring patterns](authoring-patterns.md); most should look familiar.
- Browse the [API reference](../api/wybthon.md) for the full set of primitives.
