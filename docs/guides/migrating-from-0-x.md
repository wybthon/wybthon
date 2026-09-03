# Migrating from 0.2x and 0.30

This release reworks the public API around SolidJS 2.0 semantics: typed `Prop[T]` parameters instead of a props proxy, holes instead of `dynamic()`, staged signal writes, effects that run after mount, draft-first stores, and renamed boundaries. Old names were removed rather than shimmed, so upgrading is a mechanical pass through your components. This page lists every change and shows a short before-and-after for each.

The runtime floor moved too: Wybthon now requires **Python 3.12+** in CPython and runs on **Pyodide 0.27+ / 314.x** in the browser.

## Old to new

| Old | New |
| --- | --- |
| `dynamic(fn)` | [`hole(fn)`][wybthon.hole], or just place a zero-arg callable or accessor as a child |
| `is_getter` | [`is_accessor`][wybthon.is_accessor] |
| `ErrorBoundary` | [`Errored`][wybthon.Errored] |
| `Suspense` | [`Loading`][wybthon.Loading]; content stays mounted, parked off-document, while pending |
| `LoadingList` | [`Reveal`][wybthon.Reveal] |
| `Provider` / `Theme.Provider(value=..., children=...)` | The [`Context`][wybthon.Context] object is callable: `Theme(value, *children)` |
| `forward_ref` | Removed; pass `ref=` through like any prop (`ref: Prop[Ref | None] = prop(None)`, then `input_(ref=ref.peek())`) |
| `get_props()` / `ReactiveProps` | Removed; declare parameters, each is a [`Prop[T]`][wybthon.Prop] accessor. `def Foo(props)` (a single unannotated `props` parameter, or one annotated [`Props`][wybthon.Props]) receives the mapping |
| `merge_props` / `split_props` | [`merge(*sources)`][wybthon.merge] / [`omit(props, *keys)`][wybthon.omit] |
| `on_mount` | [`on_settled`][wybthon.on_settled]; runs after the mounting flush has committed and may return a cleanup |
| `on_error` / `catch_error` | [`create_effect(..., error=handler)`][wybthon.create_effect] and `Errored(on_error=...)` |
| `create_reaction` / `Computed` | `create_effect(compute, apply)` split form / [`create_memo`][wybthon.create_memo] |
| `index_array` | [`map_array(source, fn, keyed=False)`][wybthon.map_array] |
| `map_array(source, fn, key=...)` | `map_array(source, fn, keyed=True | False | key_fn)` |
| `For(each=, children=, key=None | callable | "index")` with `(item_getter, index_getter)` | [`For(each, children, keyed=...)`][wybthon.For]: `True` (default) gives `children(item, index_accessor)`, `False` gives `children(item_accessor, index)`, a key function gives `children(item_accessor, index_accessor)` |
| `Repeat(times=...)` | [`Repeat(count, children, fallback=None, *, start=0)`][wybthon.Repeat] |
| `Show(when=..., children=...)` | [`Show(when, children, fallback=None, *, keyed=False)`][wybthon.Show]; the children callback receives the accessor (or the raw value when `keyed=True`) |
| `Match(when=..., children=...)` | [`Match(when, children, keyed=False)`][wybthon.Match] |
| `unwrap(store)` | [`snapshot(store)`][wybthon.snapshot]; new [`deep(store)`][wybthon.deep] for a tracked deep read |
| `set_store("a", "b", value)` path form | `set_store(lambda s: ...)` draft form; [`store_path("a", "b", value)`][wybthon.store_path] for the path form; [`reconcile(data, key=)`][wybthon.reconcile] |
| Store proxy `.get()` / `.keys()` / `.items()` / `.values()` | Removed (they collided with data keys); use `[]`, `in`, `len`, iteration, or `snapshot()` |
| `from wybthon import js` | Removed; `import js` yourself inside Pyodide |
| `create_effect` first run at creation | First run deferred to the next flush, after the component mounted |
| Signal writes visible immediately | Writes are staged until the next flush (microtask, end of handler, or [`flush()`][wybthon.flush]); functional updates see staged values; there's no `batch()` |
| One-parameter components inferred as "props proxy" | Only `def Foo(props)` (unannotated, named `props`) or a `Props` annotation gets the mapping |
| Python 3.9+ | Python 3.12+ (PEP 695 generics), Pyodide 0.27+ / 314.x |

New in this release: typed [`Accessor[T]`][wybthon.Accessor], [`Setter[T]`][wybthon.Setter], [`Prop[T]`][wybthon.Prop], [`Props`][wybthon.Props], and [`prop(default)`][wybthon.prop]; `Reveal(order=, tail=)`; `Loading(on=)`; `Errored(reset_on=)`; [`resolve`][wybthon.resolve], [`refresh`][wybthon.refresh], [`is_pending`][wybthon.is_pending], [`latest`][wybthon.latest]; [`action`][wybthon.action], [`create_optimistic`][wybthon.create_optimistic], [`create_optimistic_store`][wybthon.create_optimistic_store]; derived stores via `create_store(fn, seed)` and [`create_projection`][wybthon.create_projection]; `deep`, `snapshot`, `store_path`; a [`Root`][wybthon.Root] with `.dispose()` returned by `render`; root-scoped event delegation; boolean attribute handling; [`Ref`][wybthon.Ref] objects, callable refs, and lists of refs; [`wybthon.svg`][wybthon.svg] helpers; [`use_params`][wybthon.use_params], [`use_query`][wybthon.use_query], [`use_base_path`][wybthon.use_base_path]; [`a11y_control_attrs`][wybthon.a11y_control_attrs], [`error_message_attrs`][wybthon.error_message_attrs]; `WriteInScopeError` and top-level-read warnings in dev mode; a JS kernel wire protocol for batched DOM operations; template-based mounting of static subtrees.

## Components and props

Parameters replace the props proxy. Each parameter is a `Prop[T]` accessor; defaults go through `prop()`.

Before:

```python
from wybthon import component, get_props, h2


@component
def Hello(props):
    title = props.get("title", "Hi")
    return h2(title)
```

After:

```python
from wybthon import Prop, component, h2, prop


@component
def Hello(title: Prop[str] = prop("Hi")):
    return h2(title)
```

Place the prop in the tree to keep it live, or call `title()` inside a memo, effect, or hole. `title.peek()` reads once without subscribing. Extra keyword arguments still flow through `**rest`, and `merge(defaults, rest)` and `omit(rest, "class_")` replace `merge_props` and `split_props`. A component that wants the whole mapping declares `def Foo(props)` and reads `props.title` or `props["title"]`.

## Holes replace `dynamic()`

Any zero-argument callable placed as a child (or as an attribute value) is a reactive hole. `dynamic()` is gone; `hole()` exists for the rare case you need a `key`.

Before:

```python
from wybthon import dynamic, p

p("Count: ", dynamic(lambda: str(count())))
```

After:

```python
from wybthon import p

p("Count: ", count)
p("Doubled: ", lambda: count() * 2)
```

Accessors don't need wrapping at all; `str()` is applied for you.

## Flow callbacks

`For`, `Show`, `Match`, and `Repeat` take positional `each`/`when`/`count` and `children` arguments. `For`'s `key=` became `keyed=`, and the shape of the callback follows from it.

Before:

```python
from wybthon import For, Show, li, p, ul

ul(For(each=lambda: items(), children=lambda item, i: li(dynamic(lambda: item()["title"])), key=lambda t: t["id"]))
Show(when=lambda: user() is not None, children=lambda: p("Signed in"))
```

After:

```python
from wybthon import For, Show, li, p, ul

ul(For(items, lambda item, i: li(lambda: item()["title"]), keyed=lambda t: t["id"]))
Show(lambda: user() is not None, lambda u: p("Signed in as ", lambda: u()["name"]))
```

With the default `keyed=True`, rows match by identity and the callback receives the raw item plus an index accessor. `key="index"` became `keyed=False` (per-position slots, item as an accessor). `Show`'s children callback now receives an accessor for the truthy value; it can still ignore it (`lambda: ...`).

## Boundaries

`ErrorBoundary` is `Errored`, `Suspense` is `Loading`, `LoadingList` is `Reveal`. `Errored`'s fallback receives `(error, reset)`, and `reset_on=` replaces manual reset plumbing.

Before:

```python
from wybthon import ErrorBoundary, Suspense, p

Suspense(fallback=lambda: p("Loading..."), children=lambda: Dashboard())
ErrorBoundary(fallback=lambda err: p(str(err)), children=lambda: Dashboard())
```

After:

```python
from wybthon import Errored, Loading, button, current_path, div, p

Loading(lambda: Dashboard(), fallback=p("Loading..."))
Errored(
    lambda: Dashboard(),
    fallback=lambda err, reset: div(p(str(err)), button("Retry", on_click=lambda e: reset())),
    reset_on=current_path,
)
```

`Loading` now keeps the content mounted (parked off-document) while pending, so component state survives a refetch.

## Stores

Setters are draft-first: pass a function that mutates a draft. The path form lives behind `store_path`, and `unwrap` is `snapshot`. The proxy no longer exposes `.get()`, `.keys()`, `.items()`, or `.values()`, because those names collided with data keys.

Before:

```python
from wybthon import create_store, unwrap

store, set_store = create_store({"user": {"name": "Ada"}, "todos": []})
set_store("user", "name", "Grace")
raw = unwrap(store)
names = list(store.user.keys())
```

After:

```python
from wybthon import create_store, snapshot, store_path

store, set_store = create_store({"user": {"name": "Ada"}, "todos": []})


def rename(s):
    s.user.name = "Grace"
    s.todos.append({"id": 1, "title": "Ship it"})


set_store(rename)
set_store(store_path("user", "name", "Grace"))     # path form, if you prefer it
raw = snapshot(store)
names = list(snapshot(store.user))
```

Use `reconcile(data, key="id")` to merge server data while preserving row identity, and `deep(store)` in the compute stage of an effect to subscribe to the whole structure.

## Context

The `Context` object is its own provider.

Before:

```python
from wybthon import create_context

Theme = create_context("light")
Theme.Provider(value=theme, children=[App()])
```

After:

```python
from wybthon import create_context

Theme = create_context("light")
Theme(theme, App())
```

`use_context(Theme)` is unchanged and returns the value exactly as provided.

## Lifecycle

`on_mount` is `on_settled`. It runs after the flush that mounted the component committed to the DOM, so refs are assigned, and it may return a cleanup. `create_effect`'s first run also moved to after mount, and the recommended shape is the split `(compute, apply)` form; `create_reaction` and `on_error` fold into it.

Before:

```python
from wybthon import create_effect, create_reaction, on_cleanup, on_mount

on_mount(lambda: print("mounted"))
create_effect(lambda: print("count is", count()))
create_reaction(lambda: print("count changed"))(count)
```

After:

```python
from wybthon import create_effect, on_settled


def start():
    print("mounted")
    return lambda: print("unmounted")


on_settled(start)
create_effect(count, lambda value, prev: print("count is", value))
create_effect(count, lambda value, prev: print("count changed"), defer=True)
```

If an effect must react to its own failures, pass `error=handler`; rendering errors go to the nearest `Errored`.

## Signal write timing

Writes are staged until the next flush. Reading a signal right after writing it returns the committed value, not the staged one. Compose writes with functional updates, which do see staged values, and drop any `batch()` calls.

Before:

```python
from wybthon import batch, create_signal

count, set_count = create_signal(0)


def bump(e):
    with batch():
        set_count(count() + 1)
        set_count(count() + 1)   # count() saw the first write: ends at 2
```

After:

```python
from wybthon import create_signal, flush

count, set_count = create_signal(0)


def bump(e):
    set_count(lambda n: n + 1)
    set_count(lambda n: n + 1)   # updater sees the staged value: ends at 2


bump(None)
flush()                          # only needed outside a handler, for example in tests
assert count() == 2
```

Writing a signal from inside a memo, a hole, or a single-function effect now raises `WriteInScopeError` in dev mode. Move such writes into a handler, an action, `on_settled`, or the `apply` stage of a split effect.

## Python version

Type annotations use PEP 695 generics (`class Accessor[T]`, `def create_signal[T](...)`) and the `type` statement, which need Python 3.12. In the browser, target Pyodide 0.27 or newer (Python 3.12); the E2E suite pins `314.0.6` (Python 3.14).

Before:

```python
from typing import Callable, Optional

def use_value(getter: Callable[[], Optional[int]]) -> None: ...
```

After:

```python
from wybthon import Accessor

def use_value(getter: Accessor[int | None]) -> None: ...
```

Update `requires-python` in your `pyproject.toml`, and if you type-check, set `python_version = 3.12` in `mypy.ini`.

## Checklist

1. Replace `get_props()` / `ReactiveProps` with named `Prop[T]` parameters and `prop()` defaults.
2. Delete `dynamic(...)` wrappers; pass the callable or accessor directly.
3. Rename `ErrorBoundary`, `Suspense`, `LoadingList` to `Errored`, `Loading`, `Reveal`.
4. Convert `Ctx.Provider(value=..., children=[...])` to `Ctx(value, *children)`.
5. Convert `For`/`Show`/`Match`/`Repeat` keyword calls to positional, and `key=` to `keyed=`.
6. Rename `on_mount` to `on_settled`; move `create_reaction` and `on_error` into split effects.
7. Replace path-form `set_store(...)` calls with draft functions or `store_path`; `unwrap` becomes `snapshot`.
8. Replace `set_x(x() + 1)` with `set_x(lambda v: v + 1)` and remove `batch()`.
9. Bump to Python 3.12+ and re-run `mypy`.

## Next steps

- Read [Mental model](../concepts/mental-model.md) for the current model in full.
- See [Authoring patterns](authoring-patterns.md) for idiomatic component code.
- Check the [API reference](../api/wybthon.md) for signatures of every renamed primitive.
