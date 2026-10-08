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
| `function Card({ title }: CardProps)` | A [`Props`][wybthon.Props] class and `def Card(props: CardProps)` |
| `props.children` | [`ParentProps`][wybthon.ParentProps] and `props.children` |
| JSX | HTML helpers: `div(p("Hi"), class_="card")`, or `div(class_="card")[p("Hi")]` |
| `` {`Count: ${count}`} `` | A t-string: `p(t"Count: {count}")` |

## Components run once

The single biggest change. In React, your component function runs on every render, and `useState` and `useEffect` work because of hook rules. In Wybthon:

```python
from wybthon import button, component, create_signal


@component
def Counter():
    count, set_count = create_signal(0)
    print("Counter body running")
    return button(t"count: {count}", on_click=lambda: set_count(lambda n: n + 1))
```

You'll see `"Counter body running"` exactly once, no matter how many clicks. The t-string interpolating the `count` accessor becomes a *reactive hole*, so only that text node updates. Handlers may take the event or, as here, no arguments. Read [Mental model](../concepts/mental-model.md) for the formal definition.

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

In React, props are a frozen object per render, typed with an interface. In Wybthon, props are declared on a [`Props`][wybthon.Props] class, and the component takes one parameter annotated with it. Reading a [`Prop[T]`][wybthon.Prop] field returns an accessor: place it in the tree, or call it inside a reactive scope.

```tsx
type GreetProps = { name: string; excited?: boolean; onWave?: () => void };

function Greet({ name, excited = false, onWave }: GreetProps) {
  return <p onClick={onWave}>Hello, {name}{excited ? "!" : "."}</p>;
}
```

becomes

```python
from collections.abc import Callable

from wybthon import Prop, Props, component, p, prop


class GreetProps(Props):
    name: Prop[str]
    excited: Prop[bool] = prop(default=False)
    on_wave: Callable[[], None] | None = None


@component
def Greet(props: GreetProps):
    return p("Hello, ", props.name, lambda: "!" if props.excited() else ".", on_click=props.on_wave)
```

- `Prop[T]` fields are reactive. The parent can pass a plain value or an accessor, and the child stays live either way, without re-running.
- Other fields are plain data. Callbacks like `on_wave` go here; reading the field returns the function the parent passed.
- Defaults use `prop(default=...)` for `Prop[T]` fields and ordinary `= value` defaults for plain fields.
- Pyright and mypy check every call against the class, the way TypeScript checks JSX props.

Destructuring a prop into a local (`value = props.name()`) at the top of the body freezes it at mount and loses reactivity; dev mode warns about it. When you really want a one-time read (to seed local state, for example), write `props.name.peek()`.

There's no `{...rest}` catch-all: a component reads only what it declares. To forward attributes, declare them and spread the remainder with [`omit`][wybthon.omit] (`div(**omit(props, "title"))`); [`merge`][wybthon.merge] covers `{...defaults, ...props}`.

## Children

Subclass [`ParentProps`][wybthon.ParentProps] to accept children, and place `props.children` in the tree. Callers pass children with item syntax or the `children` keyword:

```python
from wybthon import ParentProps, Prop, component, h3, p, prop, section


class CardProps(ParentProps):
    title: Prop[str] = prop(default="")


@component
def Card(props: CardProps):
    return section(h3(props.title), props.children, class_="card")


Card(title="Hello")[p("Body text")]
Card(title="Hello", children=p("Body text"))
```

To inspect or reorder children, resolve them with [`children`][wybthon.children]: `kids = children(props.children)`, then `kids.to_array()`.

## Context

```jsx
const ThemeCtx = createContext("light");
<ThemeCtx.Provider value={theme}><App/></ThemeCtx.Provider>
const theme = useContext(ThemeCtx);
```

becomes

```python
from wybthon import component, create_context, create_signal, p, use_context

Theme = create_context("light")


@component
def Consumer():
    theme = use_context(Theme)  # the accessor, exactly as provided
    return p(t"Theme: {theme}")


@component
def Root():
    theme, set_theme = create_signal("dark")
    return Theme(theme, Consumer())  # the Context object is its own provider
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

With a key function, `item` is an accessor, so `Row` declares `item` as a `Prop[...]` field and stays live as the row's data changes.

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

[`on_settled`][wybthon.on_settled] is the "after mount" hook: it runs once after the flush that mounted the component, and it may return a cleanup. `ref.current` is an [`Element`][wybthon.Element]; `.element` is the raw DOM node. To forward a ref, declare it as a plain field (`ref: Ref | None = None`) and pass `ref=props.ref` down; there's no `forwardRef`.

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
    set_shown(lambda n: n + 1)  # instant UI
    await api_like()
    await refresh(likes)  # reverts to real data when the action settles
```

See [Async and Loading](../concepts/async-loading.md).

## Error boundaries

```python
from wybthon import Errored, button, div, p
from wybthon.router import current_path

Errored(
    lambda: Dashboard(),
    fallback=lambda err, reset: div(p(lambda: str(err())), button("Retry", on_click=reset)),
    reset_on=current_path,
)
```

The fallback receives `err`, an accessor for the caught error, and `reset`, which re-renders the children. `reset_on` clears the error when the given accessor changes, here on every navigation.

## Things you can stop doing

- **`useCallback` and `useMemo` for identity stability.** Closures aren't re-created.
- **`React.memo`.** Components don't re-render.
- **Hook rules and exhaustive-deps lints.** Creating state or an effect is just a function call, anywhere in the body.
- **`batch`-style wrappers.** Every write batches until the next flush.
- **`key` by index.** `For` keys rows for you; pick the strategy that fits.

## Things to watch out for

- **Don't read props or signals at the top level of the body.** `props.name()` there freezes the value (and warns). Place the accessor in the tree or read inside a memo, effect, or hole.
- **Don't expect a write to be visible immediately.** `set_x(1); x()` returns the old value until the flush. Use functional updates to compose writes.
- **Don't write signals inside a memo or a hole.** Dev mode raises `WriteInScopeError`. Write from event handlers, actions, or the `apply` stage of an effect.
- **Declare callbacks as plain fields.** A `Prop[...]` field is for values that can change. A callback goes in a plain field (`on_save: Callable[[], None] | None = None`), so reading it returns the function.
- **Define components at module scope.** Creating one inside a body doesn't cause re-renders, but it does create a new component identity on every hole re-run, which forces a remount.

## Cheat sheet

```python
from wybthon import (
    Errored,
    For,
    Loading,
    Match,
    ParentProps,
    Portal,
    Prop,
    Props,
    Ref,
    Repeat,
    Show,
    Switch,
    action,
    children,
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
from wybthon.router import Link, Route, Router, navigate
from wybthon.testing import fire, render
```

## Next steps

- Read [Mental model](../concepts/mental-model.md).
- Walk through [Authoring patterns](authoring-patterns.md) for idiomatic recipes.
- Browse [Examples](../examples.md) for complete modules.
