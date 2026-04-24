# Migrating from React

Wybthon will feel familiar to React developers, but the underlying model is intentionally different. The key shift: components run **once**, not on every render.

This guide maps common React idioms to Wybthon equivalents and calls out the pitfalls people hit most often.

## TL;DR

| React | Wybthon |
| --- | --- |
| `useState(0)` | `count, set_count = create_signal(0)` |
| `useEffect(fn, deps)` | `create_effect(fn)` |
| `useMemo(() => fn, deps)` | `create_memo(fn)` |
| `useContext(Ctx)` | `use_context(Ctx)` |
| `useRef()` | `Ref()` from `wybthon` |
| `<Suspense fallback={...} />` | [`Suspense`][wybthon.Suspense] |
| `<ErrorBoundary />` | [`ErrorBoundary`][wybthon.ErrorBoundary] |
| `lazy(() => import('./X'))` | [`lazy`][wybthon.lazy] |
| `useReducer` | `create_signal` + plain functions |

## Components run once

The single biggest change. In React, your component function runs on every render and `useState`/`useEffect` work because of hook rules. In Wybthon:

```python
@component
def Counter():
    count, set_count = create_signal(0)
    print("Counter body running")
    return button("count: ", count, on_click=lambda _e: set_count(count() + 1))
```

You'll see `"Counter body running"` exactly once, no matter how many clicks. The `count` accessor passed into `button(...)` becomes a *reactive hole*, so only that text node updates. Read [Mental model](../concepts/mental-model.md) for the formal definition.

### Implications

- No dependency arrays. Effects subscribe to whatever signals they read while running.
- No `useCallback`/`useMemo` for stability; closures don't get re-created.
- No "stale closure" bugs from missing deps.

## State and effects

```jsx
const [count, setCount] = useState(0);
useEffect(() => {
  document.title = `count ${count}`;
}, [count]);
```

becomes

```python
count, set_count = create_signal(0)
create_effect(lambda: document.title = f"count {count()}")
```

The effect re-runs because it *reads* `count()` while tracking. There's no dependency array.

## Props

In React, props are a frozen object per render. In Wybthon, every prop is a callable accessor. Pass it through; don't unpack:

```jsx
function Greet({ name }) { return <p>Hello, {name}!</p>; }
```

becomes

```python
@component
def Greet(name):
    return p("Hello, ", name, "!")
```

If you destructure a prop into a local variable, you freeze it at mount and lose reactivity. The dev-mode warning `warn_destructured_prop` will catch this.

## Context

```jsx
const ThemeCtx = createContext("light");
const theme = useContext(ThemeCtx);
```

becomes

```python
ThemeCtx = create_context("light")
theme = use_context(ThemeCtx)
```

Wybthon's [`Provider`][wybthon.Provider] is signal-backed: changing the value updates consumers without unmounting them.

## Lists

React's `array.map(item => <Row key={item.id} />)` becomes:

```python
For(each=items, children=lambda item, idx: Row(item=item, key=item().id))
```

[`For`][wybthon.For] keys by reference identity by default. Use `key=` only if you need to rekey on a derived value. See [Flow control][wybthon.For].

## Conditional rendering

Replace JSX ternaries with [`Show`][wybthon.Show]:

```python
Show(when=is_loaded, children=lambda: Profile(), fallback=lambda: Spinner())
```

`when` accepts a getter so the condition is reactive without re-rendering the whole tree.

## Refs and DOM access

```jsx
const ref = useRef(null);
useEffect(() => { ref.current.focus(); }, []);
return <input ref={ref} />;
```

becomes

```python
from wybthon import Ref, on_mount

ref = Ref()
on_mount(lambda: ref.current.focus())
return input_(ref=ref)
```

See [DOM Interop](../concepts/dom.md).

## Async data

React + Suspense is similar in spirit but Wybthon's [`create_resource`][wybthon.create_resource] is more direct:

```python
data = create_resource(query, fetch_data)

return Suspense(fallback=lambda: p("Loading"),
                children=lambda: span(lambda: data()["title"]))
```

See [Suspense and Lazy Loading](../concepts/suspense-lazy.md).

## Things you can stop doing

- **`useCallback`/`useMemo` for identity stability.** Closures aren't re-created.
- **`React.memo`.** There's nothing to memoize; components don't re-render.
- **Hook rules and exhaustive deps lints.** State/effect creation is just a function call.
- **`key` on every list item by index.** Keyed identity is automatic via `For`.

## Things to watch out for

- **Don't read props eagerly.** `name()` inside the body freezes the value. Pass `name` itself or read inside an effect.
- **Don't recreate components inside the body.** Define them at module scope. Components are cheap to mount but creating them inside a render does *not* re-render anything either way, so just define them once.
- **`if/else` in the body short-circuits.** Use `Show` / `Switch` for conditional subtrees.

## Cheat sheet

```python
from wybthon import (
    component, create_signal, create_effect, create_memo,
    on_mount, on_cleanup, Show, For, Switch, Match,
    create_context, Provider, use_context,
    Suspense, ErrorBoundary, lazy,
)
```

## Next steps

- Read [Mental model](../concepts/mental-model.md).
- Walk through [Authoring patterns](authoring-patterns.md) for idiomatic recipes.
- Browse [Examples](../examples.md) for full apps.
