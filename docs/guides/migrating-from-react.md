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
| `ref={el => ...}` | A callback ref: `ref={remember}`, where `remember(el)` receives the element |
| `useId()` | [`create_unique_id()`][wybthon.create_unique_id] |
| `<Suspense fallback={...}>` | [`Loading(children, fallback=...)`][wybthon.Loading] |
| `useTransition` / `useOptimistic` | [`action`][wybthon.action] / [`create_optimistic`][wybthon.create_optimistic] |
| `<ErrorBoundary>` | [`Errored(children, fallback=...)`][wybthon.Errored] |
| `lazy(() => import('./X'))` | [`lazy(loader)`][wybthon.lazy] |
| `createPortal(children, node)` | [`Portal(children, mount=...)`][wybthon.Portal] |
| `useReducer` | `create_signal` plus plain functions, or a [`create_store`][wybthon.create_store] with draft mutations |
| `{cond && <A/>}` / ternaries | `{Show(cond(), A(), fallback=B())}` with [`Show`][wybthon.Show], or [`Switch`][wybthon.Switch] / [`Match`][wybthon.Match] |
| `items.map(item => <Row key={item.id}/>)` | `{For(items(), row, keyed=...)}` with [`For`][wybthon.For] |
| `function Card({ title }: CardProps)` | A [`Props`][wybthon.Props] class and `def Card(props: CardProps)` |
| `props.children` | [`ParentProps`][wybthon.ParentProps] and `props.children` |
| JSX | An [`html`][wybthon.html] template: `html(t'<div class="card"><p>{message}</p></div>')` |
| `{expression}` in JSX | `{expression}` in the template; the compiler keeps calls, attribute reads, and subscripts live, as Solid's does |
| `className`, `htmlFor`, `onClick` | `class`, `for`, `onclick` (`onClick` works too) |
| `<Card title="Hi">...</Card>` | `<{Card} title="Hi">...</{Card}>`, or `{Card(title="Hi")[...]}` for full type checking |
| `<input {...attrs} />` | `<input {attrs}>` |
| `` {`Count: ${count}`} `` | `Count: {count()}` inside the template |

## Components run once

The single biggest change. In React, your component function runs on every render, and `useState` and `useEffect` work because of hook rules. In Wybthon:

```python
from wybthon import component, create_signal, html


@component
def Counter():
    count, set_count = create_signal(0)
    print("Counter body running")

    def increment():
        set_count(lambda n: n + 1)

    return html(t"<button onclick={increment}>count: {count()}</button>")
```

You'll see `"Counter body running"` exactly once, no matter how many clicks. `{count()}` in the template becomes a *reactive hole*, so only that text node updates. Handlers may take the event or, as here, no arguments. Read [Mental model](../concepts/mental-model.md) for the formal definition.

## JSX becomes templates

Markup is an HTML template written as a Python 3.14 [template string](https://peps.python.org/pep-0750/): `html(t"...")`. It's the counterpart of JSX, and Wybthon's [compiler](../concepts/compiler.md) plays the role of the JSX transform: it turns every dynamic expression in the markup into a getter, and turns each literal into a native template ahead of time. Each instance is a clone of that template, so a template costs about what the markup inside it costs. You don't run the compiler yourself: it runs in `wyb dev` and `wyb build`, in an import hook that `import wybthon` installs, and under pytest. See [Templates](../concepts/templates.md) for the full syntax.

- Attribute names are HTML names: `class`, `for`, `aria-label`, `tabindex`. Handlers are `onclick={save}`; `onClick` and `on:click` work too.
- `{expression}` works in a child, an attribute, part of an attribute (`class="btn btn-{kind()}"`), an event, a `ref`, and a spread (`<input {attrs}>`).
- Write expressions as you would in JSX: `{count() * 2}`, `{user().name}`, `class={"on" if active() else ""}`. An expression with a call, an attribute access, or a subscript stays live; a name or a constant is a value. Event handlers are never wrapped.
- Use a component with a tag, `<{Card} title={user().name}>...</{Card}>`, or call it in an interpolation, `{Card(title=user().name)}`. Either way the component receives a getter for each dynamic prop. The call form is fully type-checked; the tag form's props are checked at run time in dev mode.
- Markup the browser would silently fix is an error instead: put `<tr>` inside a `<tbody>`, and don't nest a `<div>` in a `<p>`.

If you need to build markup in code, [`h(tag, props, *children)`][wybthon.h] is the programmatic layer, like `React.createElement`.

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

In React, props are a frozen object per render, typed with an interface. In Wybthon, props are declared on a [`Props`][wybthon.Props] class with plain annotations, and the component takes one parameter annotated with it. Reading `props.name` returns the parent's current value and tracks it, as in Solid: place it in the markup, or read it inside a memo or effect.

```tsx
type GreetProps = { name: string; excited?: boolean; onWave?: () => void };

function Greet({ name, excited = false, onWave }: GreetProps) {
  return <p onClick={onWave}>Hello, {name}{excited ? "!" : "."}</p>;
}
```

becomes

```python
from collections.abc import Callable

from wybthon import Props, component, html


class GreetProps(Props):
    name: str
    excited: bool = False
    on_wave: Callable[[], None] | None = None


@component
def Greet(props: GreetProps):
    return html(t"<p onclick={props.on_wave}>Hello, {props.name}{'!' if props.excited else '.'}</p>")
```

- Every field is reactive. When the parent writes `<{Greet} name={user().name}>`, the child gets a getter and `{props.name}` follows it, without re-running the body.
- A field annotated `Callable[...]` is returned exactly as the parent passed it, so `on_wave` is the function itself.
- Defaults are ordinary `= value` defaults; use `prop(default_factory=list)` for mutable ones.
- Pyright and mypy check every call against the class, the way TypeScript checks JSX props.

Destructuring a prop into a local (`name = props.name`) at the top of the body freezes it at mount and loses reactivity; dev mode warns about it when the parent passed something reactive. When you really want a one-time read (to seed local state, for example), write `untrack(lambda: props.name)`.

There's no `{...rest}` catch-all: a component reads only what it declares. To forward attributes, declare them and spread the remainder with [`omit`][wybthon.omit] (`attrs = omit(props, "title")`, then `<div {attrs}>`); [`merge`][wybthon.merge] covers `{...defaults, ...props}`.

## Children

Subclass [`ParentProps`][wybthon.ParentProps] to accept children, and place `props.children` in the markup. Callers pass children as nested markup in the tag form, with item syntax, or with the `children` keyword:

```python
from wybthon import ParentProps, component, html


class CardProps(ParentProps):
    title: str = ""


@component
def Card(props: CardProps):
    return html(t'<section class="card"><h3>{props.title}</h3>{props.children}</section>')


html(t'<{Card} title="Hello"><p>Body text</p></{Card}>')
Card(title="Hello")[html(t"<p>Body text</p>")]
Card(title="Hello", children=html(t"<p>Body text</p>"))
```

To inspect or reorder children, resolve them with [`children`][wybthon.children]: `kids = children(lambda: props.children)`, then `kids.to_array()`.

## Context

```jsx
const ThemeCtx = createContext("light");
<ThemeCtx.Provider value={theme}><App/></ThemeCtx.Provider>
const theme = useContext(ThemeCtx);
```

becomes

```python
from wybthon import component, create_context, create_signal, html, use_context

Theme = create_context("light")


@component
def Consumer():
    theme = use_context(Theme)  # the accessor, exactly as provided
    return html(t"<p>Theme: {theme()}</p>")


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
from wybthon import For, html


def row(item, index):
    return Row(item=item)


html(t"<ul>{For(items(), row, keyed=lambda i: i['id'])}</ul>")
```

With a key function, `item` is an accessor. `Row` declares an ordinary field (`item: dict[str, Any]`), which unwraps the accessor on read, so the row stays live as its data changes.

[`For`][wybthon.For] runs the callback once per row and caches the result; reorders move DOM nodes instead of re-rendering. With a key function, the callback receives accessors for the item and the index; with the default `keyed=True`, rows match by identity and the callback gets the raw item and an index accessor. In a template, `{For(items(), row)}` hands `For` a getter for the list. In Python code, pass the accessor itself (`For(items, row)`), not a plain Python list.

## Conditional rendering

```jsx
{isLoaded ? <Profile/> : <Spinner/>}
```

becomes

```python
from wybthon import Show, html

html(t"<main>{Show(is_loaded(), Profile(), fallback=Spinner())}</main>")
```

`Show` tracks only the truthiness of `when`, so the branch re-renders when the condition flips, not on every value change. For several branches, use `Switch(Match(cond, children), ..., fallback=...)`. The built-ins work as calls in an interpolation (`{Show(ready(), panel)}`) or with the tag form (`<{Show} when={ready()}>...</{Show}>`).

## Refs and DOM access

```jsx
const ref = useRef(null);
useEffect(() => { ref.current.focus(); }, []);
return <input ref={ref} />;
```

becomes

```python
from wybthon import Ref, component, html, on_settled


@component
def AutoFocus():
    ref = Ref()
    on_settled(lambda: ref.current.element.focus())
    return html(t"<input ref={ref}>")
```

[`on_settled`][wybthon.on_settled] is the "after mount" hook: it runs once after the flush that mounted the component, and it may return a cleanup. `ref.current` is an [`Element`][wybthon.Element]; `.element` is the raw DOM node. A callback ref (`ref={remember}`) receives the `Element` instead, like React's `ref={el => ...}`. To forward a ref, declare it as a field (`ref: Ref | None = None`) and pass it down (`<input ref={props.ref}>`); there's no `forwardRef`.

## Async data

React with Suspense is similar in spirit, but Wybthon is more direct: any [`create_memo`][wybthon.create_memo] with an `async def` body is an async computation, and [`Loading`][wybthon.Loading] shows a fallback until it produces its first value:

```python
from js import fetch

from wybthon import Loading, component, create_memo, html


@component
def Title():
    async def fetch_data():
        resp = await fetch("/api/data")
        return (await resp.json()).to_py()

    data = create_memo(fetch_data)

    return Loading(html(t"<span>{data()['title']}</span>"), fallback=html(t"<p>Loading</p>"))
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
from wybthon import Errored, html
from wybthon.router import current_path


def failed(err, reset):
    return html(t"<div><p>{str(err())}</p><button onclick={reset}>Retry</button></div>")


Errored(Dashboard(), fallback=failed, reset_on=current_path)
```

The fallback receives `err`, an accessor for the caught error, and `reset`, which re-renders the children. `reset_on` clears the error when the given accessor changes, here on every navigation.

## Things you can stop doing

- **`useCallback` and `useMemo` for identity stability.** Closures aren't re-created.
- **`React.memo`.** Components don't re-render.
- **Hook rules and exhaustive-deps lints.** Creating state or an effect is just a function call, anywhere in the body.
- **`batch`-style wrappers.** Every write batches until the next flush.
- **`key` by index.** `For` keys rows for you; pick the strategy that fits.

## Things to watch out for

- **Don't read props or signals at the top level of the body.** `props.name` there freezes the value (and warns). Read it in the markup, or inside a memo or effect.
- **Don't expect a write to be visible immediately.** `set_x(1); x()` returns the old value until the flush. Use functional updates to compose writes.
- **Don't write signals inside a memo or a hole.** Dev mode raises `WriteInScopeError`. Write from event handlers, actions, or the `apply` stage of an effect.
- **Annotate callbacks as callables.** A callback field (`on_save: Callable[[], None] | None = None`) returns the function the parent passed; any other field unwraps an accessor or getter to its value.
- **Parenthesize inline handlers.** Python doesn't allow a bare `lambda` in a t-string interpolation, so `onclick={lambda: save()}` is a `SyntaxError`; write `onclick={(lambda: save())}`, or name the handler.
- **Keep templates in compiled modules.** A template in a module imported after `wybthon` is compiled automatically. A script you run directly with `python` isn't, and dev mode raises `TemplateError` when one of its dynamic expressions was evaluated only once; run it with `wyb run script.py`.
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
    html,
    lazy,
    merge,
    omit,
    on_cleanup,
    on_settled,
    prop,
    untrack,
    use_context,
)
from wybthon.router import Link, Route, Router, navigate
from wybthon.testing import fire, render
```

## Next steps

- Read [Mental model](../concepts/mental-model.md).
- Walk through [Authoring patterns](authoring-patterns.md) for idiomatic recipes.
- Browse [Examples](../examples.md) for complete modules.
