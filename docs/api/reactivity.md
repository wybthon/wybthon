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

Reactive computation (an **effect** or a **memo**) that tracks its sources
(signals and other memos) and re-runs when they change.  Also an ownership
scope: child computations created during execution are disposed before each
re-run.  When the tracked function returns an awaitable (for example an
`async def` body), the computation becomes **async**: the coroutine is
driven step by step with tracking active on every step, and the settled
value flows into the graph like a synchronous result.

Each computation carries a state for the push-mark / pull-recompute scheduler:
`CLEAN` (current), `CHECK` (a transitive source *may* have changed), or
`DIRTY` (a direct source *did* change).  A signal write pushes `DIRTY`/`CHECK`
markers out to dependents and queues affected effects; the queued effects
run on the next scheduled flush (or an explicit [`flush`][wybthon.flush]),
where they *pull* their sources up to date, which keeps updates glitch-free.

| Method | Description |
|--------|-------------|
| `_stale(state)` | Mark `CHECK`/`DIRTY` and propagate a `CHECK` to observers; queue the node (render or user effect queue) when it's an effect transitioning from `CLEAN`. |
| `_update_if_necessary()` | Resolve `CHECK` by pulling sources, then recompute if `DIRTY`. Marked `CLEAN` before recompute so a re-entrant self-write reschedules it. |
| `_update()` | Dispose children and cleanups, rebuild the dependency set, and re-execute the function under `_current_owner = _current_observer = self`. For memos, store the new value and escalate observers to `DIRTY` only when it changed. |
| `dispose()` | Unsubscribe from all sources, drop self as a source for any observers, dispose children, run cleanups. |

#### Public API

##### Signals-first API (recommended)

- `create_signal(value, *, equals=...) -> (getter, setter)`. Optional **`equals`**: default uses **value equality** (`==`) with an identity (`is`) fast-path; `equals=True` is equivalent to the default; `equals=False` notifies on every `set()`; `equals=fn` with `fn(old, new) -> bool` skips notification when `fn` returns `True` (custom comparator).  Use `equals=lambda a, b: a is b` for SolidJS-style identity-only semantics.  The getter exposes **`.peek()`** for untracked reads.  The setter also accepts an **updater function**: `set_count(lambda n: n + 1)` computes the new value from the previous one and returns the value it stored.  Writes apply **immediately** (reads see the new value right away); dependent effects are batched automatically and run on the next flush.
- `create_effect(fn) -> Computation` or `create_effect(compute, apply) -> Computation`. The effect runs once at creation and re-runs (on flush) when a tracked source changes.  In the **split form**, `compute` runs tracked and its return value is passed to `apply`, which runs **untracked** (and optionally receives the previous computed value as a second parameter), so incidental reads in the side-effect stage can't over-subscribe the effect.  In the single-function form, if `fn` accepts a positional parameter it receives the **previous return value** on each re-execution.  Either stage's function may be `async def`: awaits suspend the effect without blocking, and reads after an `await` are still tracked.  The returned `Computation` is added as a child of the current owner.  Inside a component's setup phase the owner is the `_ComponentContext` (effect survives re-renders, disposed on unmount).  Inside a render function the owner is the render `Computation` (effect disposed on re-render).  User effects run **after** render effects and after the DOM commit in each flush, matching Solid's `createEffect` timing.
- `create_render_effect(fn) -> Computation` or `create_render_effect(compute, apply) -> Computation`. Like `create_effect` (including the split form), but queued in the render phase: it runs before the DOM commit and before user effects in each flush.  The framework uses this internally for DOM bindings; use it when an effect must run during the render phase.
- `create_memo(fn, *, equals=...) -> getter`. Creates a lazy memo `Computation` under the current owner; recomputes only when read after a source changed, and is disposed when the owner is disposed.  Optional **`equals`** (same semantics as `create_signal`) controls when the memo's own observers are notified after a recompute.  The getter exposes **`.peek()`** for untracked reads.  When `fn` is an **`async def`** (or returns an awaitable), the memo becomes an async computation; see [Async computations](#async-computations) below.
- `flush()`. Runs all pending effects now: render effects first, then a single batched DOM commit across the Pyodide bridge, then user effects.  Signal writes apply immediately, but dependent effects run on the next scheduled flush; in the browser that happens automatically on a microtask (and at the end of every event handler dispatched through Wybthon's event system).  Call `flush()` when you need the effects *now*, for example right after a write in synchronous test code.  Safe to call at any time; a no-op when nothing is pending.
- `create_reaction(on_invalidate) -> track`. On-change reaction with manual tracking, mirroring Solid's `createReaction`.  Call `track(fn)` to run `fn` with tracking; the **first** change to any tracked dependency fires `on_invalidate` (untracked) and stops tracking until `track` is called again.
- `on_error(handler)`. Registers an error handler on the current reactive owner scope, mirroring Solid's `onError`.  Exceptions raised by child computations route to the nearest ancestor handler; multiple handlers in one scope chain in registration order.
- `create_unique_id() -> str`. Returns a unique, stable ID string (`"wyb-0"`, `"wyb-1"`, ...) for wiring `for`/`aria-*` attributes, mirroring Solid's `createUniqueId`.
- `catch_error(fn, handler) -> result | None`. Runs `fn` under a scope whose errors (including errors thrown later by effects created inside it) route to `handler` instead of propagating.  Mirrors Solid's `catchError`.
- `on_mount(fn)`. Run after first render.
- `on_cleanup(fn)`. Appends `fn` to the current owner's cleanup list.  Inside `create_effect`: runs before each re-execution and on disposal.  Inside a component's setup phase: runs when the component unmounts.

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

##### Split effects

The two-argument form of `create_effect` (and `create_render_effect`)
separates the tracked *compute* stage from the untracked *apply* stage,
matching SolidJS 2.0's `createEffect(compute, apply)`.  It replaces the
old `on(deps, fn)` helper:

```python
from wybthon import create_effect

# Track only a() and b(); the apply stage runs untracked.
create_effect(lambda: (a(), b()), lambda pair: print("changed:", pair))

# The apply stage may also take the previous computed value.
create_effect(count, lambda value, prev: print(prev, "->", value))
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
otherwise each parameter is bound to its own accessor and there's no
need to call `get_props()`.

`ReactiveProps` is read-only; the parent/reconciler updates underlying
values.  When a parent passes a getter (e.g., `name=my_signal`), the
proxy unwraps it transparently, and children always read with `props.name()`.

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

`children(getter)` wraps a zero-argument callable that returns the children value (often `lambda: get_props().children()`) and returns a **memo getter** that flattens and resolves the list. Matches Solid's `children()` helper. Import under an alias (e.g., `from wybthon import children as resolve_children`) if your component also names a parameter `children`.

```python
from wybthon import children, component, dynamic, get_props, h3, section

@component
def Card(title=""):
    props = get_props()
    resolved = children(lambda: props.children())
    return section(h3(dynamic(lambda: props.title())), *resolved(), class_="card")
```

##### Async computations

Async data flows through ordinary memos: `create_memo(async_fn)` creates
an **async memo**.  Signal reads inside the coroutine are tracked both
before and after `await` points, so the memo refetches when its
dependencies change.

- Reading an async memo **before its first value** raises
  **`NotReadyError`**.  The error propagates through derived sync memos
  (they become pending too) and suspends effects that read pending
  values; the nearest [`Loading`][wybthon.Loading] boundary turns it
  into fallback UI.  Application code rarely raises or catches it
  directly.
- Once the memo has a value, recomputes serve the **stale value while
  revalidating**: reads during an in-flight recompute return the
  previous value instead of suspending.
- Errors raised by the async body are stored and re-raised on read.
- `is_pending(getter) -> bool`. Tracked read reporting in-flight
  recomputation: returns `True` while any async computation read by
  `getter` has a recompute in flight.  A read that raises
  `NotReadyError` also counts as pending (and is swallowed).  Use it to
  render "refreshing" hints without tearing content down.
- `latest(getter)`. Reads without ever raising `NotReadyError`:
  not-ready reads return their most recent settled value, or `None`
  before the first value.  Use it to peek at data outside a `Loading`
  boundary.

```python
from wybthon import create_memo, is_pending, latest

async def fetch_user():
    resp = await js.fetch("/api/user")
    return await resp.json()

user = create_memo(fetch_user)

span(lambda: "Refreshing..." if is_pending(user) else "")
name = latest(lambda: user()["name"])  # None until the first value
```

##### Actions and optimistic state

- `action(fn) -> wrapper`. Decorator (or plain wrapper) for an async
  mutation.  Calling the wrapper schedules `fn` as a task; the action
  counts as **in flight** until it settles.  The wrapper's
  **`.pending()`** getter is a tracked read that returns `True` while
  any run of the action is in flight.  Errors route to the nearest
  error-boundary scope captured at call time and re-raise to the
  awaiter, so `await my_action(...)` behaves like a normal call.
- `create_optimistic(source) -> (getter, setter)`. Overlays a signal:
  writes through the setter show immediately, and the override
  **reverts to the source value** when all in-flight actions settle.
  `source` may be a zero-arg getter (live reactive source) or a plain
  initial value.  The setter supports functional updates, like a signal
  setter.

```python
from wybthon import action, create_memo, create_optimistic

likes = create_memo(fetch_like_count)          # async source
shown, set_shown = create_optimistic(likes)    # shadows it

@action
async def like():
    set_shown(lambda n: (n or 0) + 1)  # instant UI
    await api_like()                    # reverts to real data on settle

span(lambda: "Saving..." if like.pending() else "")
```

See also [`create_optimistic_store`][wybthon.create_optimistic_store]
for the store version.

##### Reactive utilities

- `untrack(fn)`. Run without tracking signal reads.
- `create_root(fn)`. Creates an independent `Owner` root.  `fn` receives a `dispose` callback that tears down the root and all its children.  Effects created inside the root are owned by it and cleaned up on `dispose()`.
- `merge_props(*sources)`. Merge prop sources into a **reactive proxy**.  Each source may be a plain ``dict``, a callable getter, or another proxy.  Reads are lazy: callable sources are called on each access for signal tracking.  Returns an object supporting ``[]``, ``.get()``, ``in``, ``len()``, iteration, and ``==`` comparison with dicts.
- `split_props(props, *key_groups)`. Split a props source into **reactive proxy** groups by key name, plus a rest group.  Returns ``(group1, ..., rest)``; each proxy lazily reads from the original source.

##### Reactive list primitives

- `map_array(source, map_fn, *, key=None)`. Keyed reactive list mapping.  ``source`` is a getter returning a list; ``map_fn(item_getter, index_getter)`` runs once per unique item.  Items match by **reference identity** by default, or by ``key(item)`` when a key extractor is given: an item whose key survives a data refresh keeps its scope and DOM, and only its ``item_getter`` signal updates.  Returns a getter producing the mapped list.  Per-item reactive scopes are created and disposed automatically.
- `index_array(source, map_fn)`. Index-keyed reactive list mapping.  Like ``map_array`` but keyed by index position.  ``map_fn(item_getter, index: int)``: the item getter is a signal that updates in place.  Returns a getter producing the mapped list.
- `create_selector(source)`. Efficient selection signal.  Returns ``is_selected(key) -> bool``.  When the source changes, only the previous and new key's dependents re-run (O(1) instead of O(n)).

##### Global state

Two module globals drive tracking. `_current_owner` is the active ownership
scope: effects and memos created while it's set become its children.
`_current_observer` is the computation currently recording dependencies: a
signal or memo read while it's set subscribes that observer. `Computation._update()`
sets both to `self` while it executes, so reads link to the running
computation and newly created scopes are owned by it. A signal write marks
the graph stale and schedules a flush; the flush runs pending render
effects, commits the batched DOM ops once across the bridge, then runs user
effects. In the browser the flush is scheduled on a microtask (and runs at
the end of every dispatched event handler); elsewhere pending work waits
for an explicit [`flush`][wybthon.flush] call.

Type hints are provided for all public functions and classes.
