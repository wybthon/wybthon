# Migrating from Solid

Wybthon is essentially SolidJS for Python. Most of the primitives have direct equivalents and the mental model is identical: components run once, signals drive fine-grained updates, and the ownership tree manages cleanup.

The differences are mostly cosmetic: Python instead of JavaScript, builder functions instead of JSX, and a few naming conventions to keep things idiomatic.

## API mapping

| SolidJS | Wybthon |
| --- | --- |
| `createSignal(initial)` | [`create_signal(initial)`][wybthon.create_signal] |
| `createEffect(fn)` | [`create_effect(fn)`][wybthon.create_effect] |
| `createMemo(fn)` | [`create_memo(fn)`][wybthon.create_memo] |
| `createResource(source, fetcher)` | [`create_resource(source, fetcher)`][wybthon.create_resource] |
| `createContext(default)` / `useContext` | [`create_context`][wybthon.create_context] / [`use_context`][wybthon.use_context] |
| `<Show when={...} fallback={...}>` | [`Show(when=..., fallback=...)`][wybthon.Show] |
| `<For each={...}>` | [`For(each=..., children=...)`][wybthon.For] |
| `<Index each={...}>` | [`Index(each=..., children=...)`][wybthon.Index] |
| `<Switch>` / `<Match>` | [`Switch`][wybthon.Switch] / [`Match`][wybthon.Match] |
| `<Dynamic component={...} />` | [`Dynamic(component=...)`][wybthon.Dynamic] |
| `<Portal mount={...}>` | [`create_portal(mount=...)`][wybthon.create_portal] |
| `<ErrorBoundary fallback={...}>` | [`ErrorBoundary(fallback=...)`][wybthon.ErrorBoundary] |
| `<Suspense fallback={...}>` | [`Suspense(fallback=...)`][wybthon.Suspense] |
| `lazy(() => import(...))` | [`lazy(load=...)`][wybthon.lazy] |
| `onMount(fn)` | [`on_mount(fn)`][wybthon.on_mount] |
| `onCleanup(fn)` | [`on_cleanup(fn)`][wybthon.on_cleanup] |
| `batch(fn)` | [`batch(fn)`][wybthon.batch] |
| `untrack(fn)` | [`untrack(fn)`][wybthon.untrack] |
| `on(deps, fn)` | [`on(deps, fn)`][wybthon.on] |
| `createStore(initial)` | [`create_store(initial)`][wybthon.create_store] |
| `produce(fn)` | [`produce(fn)`][wybthon.produce] |

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

For ergonomic prop manipulation Wybthon offers [`get_props`][wybthon.get_props] (analogous to Solid's `splitProps`):

```python
from wybthon import get_props

@component
def Button(label, **rest):
    props, others = get_props(rest, ["disabled"])
    return button(label, disabled=props["disabled"], **others)
```

## Signals and effects

Identical in spirit and behavior:

```python
count, set_count = create_signal(0)
create_effect(lambda: print("count =", count()))
```

`create_effect` re-runs whenever signals it tracked during the previous run change. There is no manual dep array.

## Stores

```python
from wybthon import create_store, produce

state, set_state = create_store({"count": 0, "items": []})

# atomic update:
with produce(state) as draft:
    draft["count"] += 1
    draft["items"].append("new")
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

Wybthon's router supports nested routes, dynamic params, query parsing, and lazy components — see [Routing][wybthon.Router].

## What's intentionally different

- **Naming.** snake_case across the API (`create_signal`, not `createSignal`). Component names stay PascalCase.
- **Imports.** Pull from `wybthon` (and optionally `wybthon.html` for tag helpers).
- **`Dynamic`.** Use `dynamic(lambda: ...)` to inline a reactive computation; component-style `Dynamic` exists too.
- **JS interop.** Use `pyodide.ffi` to talk to the host. See [Pyodide guide](pyodide.md).

## What carries over directly

- The mental model (components run once, fine-grained reactivity).
- Ownership semantics — `on_cleanup` attaches to the current owner.
- Transitions and resources — `create_resource` integrates with `Suspense`.
- Patterns like keyed lists, conditional flows, and nested boundaries.

## Next steps

- Read [Mental model](../concepts/mental-model.md) for the framework's core ideas.
- Explore [Authoring patterns](authoring-patterns.md) — many should look familiar.
- Browse the [API reference](../api/wybthon.md) for the full set of primitives.
