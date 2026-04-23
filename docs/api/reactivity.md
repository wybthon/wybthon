### wybthon.reactivity

::: wybthon.reactivity

#### Ownership classes

##### `Owner`

Base reactive ownership scope.  Tracks child owners and cleanup callbacks.

| Attribute | Description |
|-----------|-------------|
| `_parent` | Parent `Owner` or `None` for roots. |
| `_children` | List of child `Owner` instances. |
| `_cleanups` | Callbacks run on disposal (LIFO order). |
| `_context_map` | Optional dict mapping context IDs to values (used by `Provider`). |

| Method | Description |
|--------|-------------|
| `dispose()` | Dispose children depth-first, run own cleanups, detach from parent. |
| `_lookup_context(ctx_id, default)` | Walk up the owner chain to find a context value. |
| `_set_context(ctx_id, value)` | Store a context value on this owner. |

##### `Computation(Owner)`

Reactive computation that tracks `Signal` reads and re-runs when they
change.  Also an ownership scope: child computations created during
execution are disposed before each re-run.

| Method | Description |
|--------|-------------|
| `run()` | Dispose children and cleanups, clear deps, re-execute the function under `_current_owner = self`. |
| `schedule()` | Enqueue a re-run on the next flush. |
| `dispose()` | Cancel subscriptions, clear deps, remove from pending queue, run cleanups. |

#### Public API

##### Signals-first API (recommended)

- `create_signal(value, *, equals=...) -> (getter, setter)` — optional **`equals`**: default uses **value equality** (`==`) with an identity (`is`) fast-path; `equals=True` is equivalent to the default; `equals=False` notifies on every `set()`; `equals=fn` with `fn(old, new) -> bool` skips notification when `fn` returns `True` (custom comparator).  Use `equals=lambda a, b: a is b` for SolidJS-style identity-only semantics.
- `create_effect(fn) -> Computation` — the returned `Computation` is added as a child of the current owner.  Inside a component's setup phase the owner is the `_ComponentContext` (effect survives re-renders, disposed on unmount).  Inside a render function the owner is the render `Computation` (effect disposed on re-render).  Supports previous value: `create_effect(lambda prev: ...)`.
- `create_memo(fn) -> getter` — creates a `Computation` under the current owner; disposed when the owner is disposed.
- `on_mount(fn)` — run after first render
- `on_cleanup(fn)` — appends `fn` to the current owner's cleanup list.  Inside `create_effect`: runs before each re-execution and on disposal.  Inside a component's setup phase: runs when the component unmounts.
- `batch() -> context manager` or `batch(fn) -> result` — callback form flushes synchronously

##### `create_signal` and `equals`

```python
from wybthon import create_signal

# Default: value equality (==) with an identity (is) fast-path.
# Re-setting an unchanged value is a no-op; a new container with
# value-equal contents also skips.  Mutating the same list/dict in
# place and re-setting the same reference is a no-op too -- copy
# the container first or pass ``equals=False`` to force notification.
x, set_x = create_signal({"a": 1})

# Equivalent to the default.
y, set_y = create_signal(0, equals=True)

# Always notify subscribers, even when the value is unchanged.
z, set_z = create_signal(0, equals=False)

# SolidJS-style identity-only semantics: notify whenever the new
# reference is not the same Python object as the old.
w, set_w = create_signal([], equals=lambda old, new: old is new)
```

##### `ReactiveProps` and `get_props()`

`get_props()` returns the **`ReactiveProps`** proxy for the current
`@component` instance.  The proxy exposes one consistent shape for
every prop:

* `props.name` (attribute) or `props["name"]` (item) returns a
  **stable zero-arg accessor**.  Calling the accessor reads the
  current value (tracked when called inside an effect or hole).
  Embedding it in a VNode tree creates a reactive auto-hole.
* `props.value(name, default=None)` reads the current value
  immediately (a one-shot, untracked-friendly snapshot).
* The proxy supports `in`, `len()`, iteration, and `==` against
  dicts.

```python
from wybthon import component, create_effect, dynamic, get_props, p

@component
def Greeting(name="world"):
    props = get_props()
    create_effect(lambda: print("name is now", props.name()))
    return p(dynamic(lambda: f"Hello, {props.name()}!"))
```

When a component declares a single positional parameter with no
default, the decorator passes the proxy in directly (proxy mode);
otherwise each parameter is bound to its own accessor and there is no
need to call `get_props()`.

`ReactiveProps` is read-only; the parent/reconciler updates underlying
values.  When a parent passes a getter (e.g. `name=my_signal`), the
proxy unwraps it transparently — children always read with `props.name()`.

##### `get_owner()` and `run_with_owner(owner, fn)`

After an `await`, the reactive owner stack may no longer match the component that started the work. Capture the owner before awaiting and restore it when creating effects or other scoped work:

```python
from wybthon import create_effect, get_owner, run_with_owner

async def load():
    owner = get_owner()
    data = await fetch_something()
    run_with_owner(owner, lambda: create_effect(lambda: use(data)))
```

##### `children(fn)`

`children(getter)` wraps a zero-argument callable that returns the children value (often `lambda: get_props().children()`) and returns a **memo getter** that flattens and resolves the list. Matches Solid’s `children()` helper. Import under an alias (e.g. `from wybthon import children as resolve_children`) if your component also names a parameter `children`.

```python
from wybthon import children, component, dynamic, get_props, h3, section

@component
def Card(title=""):
    props = get_props()
    resolved = children(lambda: props.children())
    return section(h3(dynamic(lambda: props.title())), *resolved(), class_="card")
```

##### Resources

- `create_resource(fetcher) -> Resource`
- `create_resource(source, fetcher) -> Resource` — refetches when source changes

##### Reactive utilities

- `untrack(fn)` — run without tracking signal reads
- `on(deps, fn, defer=False)` — effect with explicit deps
- `create_root(fn)` — creates an independent `Owner` root.  `fn` receives a `dispose` callback that tears down the root and all its children.  Effects created inside the root are owned by it and cleaned up on `dispose()`.
- `merge_props(*sources)` — merge prop sources into a **reactive proxy**.  Each source may be a plain ``dict``, a callable getter, or another proxy.  Reads are lazy: callable sources are called on each access for signal tracking.  Returns an object supporting ``[]``, ``.get()``, ``in``, ``len()``, iteration, and ``==`` comparison with dicts.
- `split_props(props, *key_groups)` — split a props source into **reactive proxy** groups by key name, plus a rest group.  Returns ``(group1, ..., rest)``; each proxy lazily reads from the original source.

##### Reactive list primitives

- `map_array(source, map_fn)` — keyed reactive list mapping.  ``source`` is a getter returning a list; ``map_fn(item_getter, index_getter)`` runs once per unique item (matched by reference identity).  Returns a getter producing the mapped list.  Per-item reactive scopes are created and disposed automatically.
- `index_array(source, map_fn)` — index-keyed reactive list mapping.  Like ``map_array`` but keyed by index position.  ``map_fn(item_getter, index: int)`` — the item getter is a signal that updates in place.  Returns a getter producing the mapped list.
- `create_selector(source)` — efficient selection signal.  Returns ``is_selected(key) -> bool``.  When the source changes, only the previous and new key's dependents re-run (O(1) instead of O(n)).

##### Global state

A single `_current_owner` global tracks the active ownership scope.
When a `Computation.run()` executes, it sets `_current_owner = self` so
that any effects or memos created during execution become its children.

Type hints are provided for all public functions and classes.
