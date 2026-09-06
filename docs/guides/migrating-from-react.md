# Migrating from React

Wybthon will feel familiar to React developers, but the underlying model is intentionally different. The key shift: components run **once**, not on every render, and updates flow through signals into small reactive expressions in the tree.

This guide maps common React idioms to Wybthon equivalents and calls out the pitfalls people hit most often.

## TL;DR

| React | Wybthon |
| --- | --- |
| `const [count, setCount] = useState(0)` | `count, set_count = create_signal(0)` |
| `useEffect(fn, deps)` | [`create_effect(compute, apply)`][wybthon.create_effect]; dependencies are whatever `compute` reads |
| `useMemo(() => fn, deps)` | [`create_memo(fn)`][wybthon.create_memo] |
| `useContext(Ctx)` / `<Ctx.Provider value>` | [`use_context(Ctx)`][wybthon.use_context] / `Ctx(value, *children)` |
| `useRef()` | [`Ref()`][wybthon.Ref] |
| `useId()` | [`create_unique_id()`][wybthon.create_unique_id] |
| `<Suspense fallback={...}>` | [`Loading(children, fallback=...)`][wybthon.Loading] |
| `useTransition` / `useOptimistic` | [`action`][wybthon.action] / [`create_optimistic`][wybthon.create_optimistic] |
| `<ErrorBoundary>` | [`Errored(children, fallback=...)`][wybthon.Errored] |
| `lazy(() => import('./X'))` | [`lazy(loader)`][wybthon.lazy] |
| `createPortal(children, node)` | [`Portal(children, mount=...)`][wybthon.Portal] |
| `useReducer` | `create_signal` plus plain functions, or a [`create_store`][wybthon.create_store] with draft mutations |
| `{cond && <A/>}` / ternaries | [`Show`][wybthon.Show], [`Switch`][wybthon.Switch] / [`Match`][wybthon.Match] |
| `items.map(item => <Row key={item.id}/>)` | [`For(items, lambda item, i: Row(...), keyed=...)`][wybthon.For] |
| JSX | HTML helpers: `div(p("Hi"), class_="card")` |

## Components run once

The single biggest change. In React, your component function runs on every render, and `useState` and `useEffect` work because of hook rules. In Wybthon:

```python
from wybthon import button, component, create_signal


@component
def Counter():
    count, set_count = create_signal(0)
    print("Counter body running")
    return button("count: ", count, on_click=lambda e: set_count(lambda n: n + 1))
```

You'll see `"Counter body running"` exactly once, no matter how many clicks. The `count` accessor placed inside `button(...)` becomes a *reactive hole*, so only that text node updates. Read [Mental model](../concepts/mental-model.md) for the formal definition.

### Implications

- No dependency arrays. Effects subscribe to whatever signals they read while running.
- No `useCallback`, `useMemo`, or `React.memo` for stability; closures aren't re-created because the body doesn't re-run.
- No stale-closure bugs from missing deps.
- `if`/`else` in the body runs once. Use `Show` or `Switch` for conditions that should follow state.

## State and effects

```jsx
const [count, setCount] = useState(0);
useEffect(() => {
  document.title = `count ${count}`;
}, [count]);
```

becomes

```python
from js import document

from wybthon import create_effect, create_signal

count, set_count = create_signal(0)


def set_title(value: int, prev: int | None) -> None:
    document.title = f"count {value}"


create_effect(count, set_title)
```

The split form `create_effect(compute, apply)` is the closest analogue to `useEffect`'s deps-then-body structure: `compute` runs tracked and declares the dependencies (here the `count` accessor itself), and `apply` runs untracked with the value. `apply` may return a cleanup, like `useEffect`'s return value. Effects run after the DOM commit, and the first run happens after the component mounted.

Signal writes are **staged**: after `set_count(1)`, `count()` still returns the old value until the graph flushes at the end of the event handler. That's why the counter above uses `set_count(lambda n: n + 1)`, the equivalent of React's `setCount(n => n + 1)`, and it composes the same way.

## Props

In React, props are a frozen object per render. In Wybthon, every prop is a [`Prop[T]`][wybthon.Prop] accessor bound to a parameter. Place it in the tree, or call it inside a reactive scope:

```jsx
function Greet({ name, excited = false }) {
  return <p>Hello, {name}{excited ? "!" : "."}</p>;
}
```

becomes

```python
from wybthon import Prop, component, p, prop


@component
def Greet(name: Prop[str], excited: Prop[bool] = prop(False)):
    return p("Hello, ", name, lambda: "!" if excited() else ".")
```

Destructuring a prop into a local (`value = name()`) at the top of the body freezes it at mount and loses reactivity; dev mode warns about it. When you really want a one-time read (to seed local state, for example), write `name.peek()`.

`{...rest}` spreading works the same way: declare `**rest` and forward it with `div(**rest)`. [`merge`][wybthon.merge] and [`omit`][wybthon.omit] cover `{...defaults, ...props}` and "everything except these keys".

## Children

`props.children` is a normal prop. Positional arguments to a component call become `children`:

```python
from wybthon import Prop, component, h3, prop, section
from wybthon import children as resolve_children


@component
def Card(title: Prop[str] = prop(""), children: Prop = prop(None)):
    return section(h3(title), resolve_children(children), class_="card")


Card("Body text", title="Hello")
```

## Context

```jsx
const ThemeCtx = createContext("light");
<ThemeCtx.Provider value={theme}><App/></ThemeCtx.Provider>
const theme = useContext(ThemeCtx);
```

becomes

```python
from wybthon import component, create_context, create_signal, use_context

Theme = create_context("light")


@component
def Root():
    theme, set_theme = create_signal("dark")
    return Theme(theme, App())      # the Context object is its own provider


@component
def Consumer():
    theme = use_context(Theme)      # the accessor, exactly as provided
    return p(lambda: f"Theme: {theme()}")
```

Pass an accessor as the value and consumers update without unmounting.

## Lists

```jsx
{items.map(item => <Row key={item.id} item={item} />)}
```

becomes

```python
from wybthon import For, ul

ul(For(items, lambda item, index: Row(item=item), keyed=lambda i: i["id"]))
```

[`For`][wybthon.For] runs the callback once per row and caches the result; reorders move DOM nodes instead of re-rendering. With a key function, the callback receives accessors for the item and the index; with the default `keyed=True`, rows match by identity and the callback gets the raw item and an index accessor. Always pass an accessor (or a store path) for the list, not a plain Python list.

## Conditional rendering

```jsx
{isLoaded ? <Profile/> : <Spinner/>}
```

becomes

```python
from wybthon import Show

Show(is_loaded, lambda: Profile(), fallback=lambda: Spinner())
```

`Show` tracks only the truthiness of `when`, so the branch re-renders when the condition flips, not on every value change. For several branches, use `Switch(Match(cond, children), ..., fallback=...)`.

## Refs and DOM access

```jsx
const ref = useRef(null);
useEffect(() => { ref.current.focus(); }, []);
return <input ref={ref} />;
```

becomes

```python
from wybthon import Ref, component, input_, on_settled


@component
def AutoFocus():
    ref = Ref()
    on_settled(lambda: ref.current.element.focus())
    return input_(ref=ref)
```

[`on_settled`][wybthon.on_settled] is the "after mount" hook: it runs once after the flush that mounted the component, and it may return a cleanup. `ref.current` is an [`Element`][wybthon.Element]; `.element` is the raw DOM node. To forward a ref, accept it as an ordinary prop (`ref: Prop[Ref | None] = prop(None)`) and pass `ref=ref.peek()` down; there's no `forwardRef`.

## Async data

React with Suspense is similar in spirit, but Wybthon is more direct: any [`create_memo`][wybthon.create_memo] with an `async def` body is an async computation, and [`Loading`][wybthon.Loading] shows a fallback until it produces its first value:

```python
from js import fetch

from wybthon import Loading, component, create_memo, p, span


@component
def Title():
    async def fetch_data():
        resp = await fetch("/api/data")
        return (await resp.json()).to_py()

    data = create_memo(fetch_data)

    return Loading(
        lambda: span(lambda: data()["title"]),
        fallback=p("Loading"),
    )
```

Later recomputes run as transitions, holding the dependent UI on the previous state until the new value lands, so the boundary doesn't flash and nothing tears; [`is_pending`][wybthon.is_pending] tells you when that's happening. For mutations, [`action`][wybthon.action] and [`create_optimistic`][wybthon.create_optimistic] cover what `useTransition` and `useOptimistic` do in React:

```python
from wybthon import action, create_optimistic, refresh

shown, set_shown = create_optimistic(likes)


@action
async def like():
    set_shown(lambda n: n + 1)   # instant UI
    await api_like()
    await refresh(likes)         # reverts to real data when the action settles
```

See [Async and Loading](../concepts/async-loading.md).

## Error boundaries

```python
from wybthon import Errored, button, div, p

Errored(
    lambda: Dashboard(),
    fallback=lambda err, reset: div(p(str(err)), button("Retry", on_click=lambda e: reset())),
    reset_on=current_path,
)
```

## Things you can stop doing

- **`useCallback` and `useMemo` for identity stability.** Closures aren't re-created.
- **`React.memo`.** Components don't re-render.
- **Hook rules and exhaustive-deps lints.** Creating state or an effect is just a function call, anywhere in the body.
- **`batch`-style wrappers.** Every write batches until the next flush.
- **`key` by index.** `For` keys rows for you; pick the strategy that fits.

## Things to watch out for

- **Don't read props or signals at the top level of the body.** `name()` there freezes the value (and warns). Place the accessor in the tree or read inside a memo, effect, or hole.
- **Don't expect a write to be visible immediately.** `set_x(1); x()` returns the old value until the flush. Use functional updates to compose writes.
- **Don't write signals inside a memo or a hole.** Dev mode raises `WriteInScopeError`. Write from event handlers, actions, or the `apply` stage of an effect.
- **Define components at module scope.** Creating one inside a body doesn't cause re-renders, but it does create a new component identity on every hole re-run, which forces a remount.

## Cheat sheet

```python
from wybthon import (
    Errored,
    For,
    Loading,
    Match,
    Portal,
    Prop,
    Props,
    Ref,
    Repeat,
    Show,
    Switch,
    action,
    component,
    create_context,
    create_effect,
    create_memo,
    create_optimistic,
    create_signal,
    create_store,
    lazy,
    merge,
    omit,
    on_cleanup,
    on_settled,
    prop,
    use_context,
)
```

## Next steps

- Read [Mental model](../concepts/mental-model.md).
- Walk through [Authoring patterns](authoring-patterns.md) for idiomatic recipes.
- Browse [Examples](../examples.md) for complete modules.
