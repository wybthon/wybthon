### Reactivity

Signals drive the render pipeline.

```python
from wybthon import create_signal, create_effect, create_memo, flush

count, set_count = create_signal(0)
double = create_memo(lambda: count() * 2)

create_effect(lambda: print("double:", double()))  # prints "double: 0"
set_count(1)   # double() == 2 immediately (memos are pull-based)
flush()        # prints "double: 2" (effects run on the next flush)
```

In the browser the flush happens automatically on a microtask (and at the end of every event handler), so application code rarely calls `flush()` directly. See [Automatic batching](#automatic-batching) below.

- `create_signal(value, *, equals=...)` returns a `(getter, setter)` tuple.
  The setter accepts either a new value or an **updater function**
  (`set_count(lambda n: n + 1)`). The getter exposes `.peek()` for
  untracked reads. By default `equals` uses **value equality** (`==`)
  with an identity fast-path; pass `equals=False` to fire on every set,
  or a custom comparator (e.g., `equals=lambda a, b: a is b` for
  SolidJS-style identity-only semantics). See
  [Reactivity API](../api/reactivity.md).
- `create_memo(fn, *, equals=...)` returns a derived getter; recomputes **lazily** on read after a dependency changes. `fn` may be an `async def`, which makes the memo an [async computation](#async-memos). `equals` controls when its observers are notified; the getter also exposes `.peek()`.
- `create_effect(fn)` runs once immediately and re-runs on the next flush after a dependency changes; it supports the previous return value as an optional argument. `create_effect(compute, apply)` is the **split form**: `compute` runs tracked and its return value is passed to the untracked `apply` stage. Effects may be `async def`. User effects run after the DOM commit in each flush.
- `create_render_effect(fn)` is like `create_effect` but runs in the **render phase**, before the DOM commit and before user effects (the framework's own DOM bindings live here). It supports the same split form.
- `create_reaction(on_invalidate)` returns a `track(fn)` function; the first change to a dependency tracked by `fn` fires `on_invalidate` once (on the next flush), then tracking stops until you call `track` again.
- `flush()` runs pending render effects, commits the batched DOM ops once across the Pyodide bridge, then runs user effects. Automatic in the browser; call it explicitly in plain Python scripts and tests.
- `is_pending(getter)` is a tracked read reporting whether an async computation has a recompute in flight; `latest(getter)` reads without raising `NotReadyError`.
- `action(fn)` wraps an async mutation and tracks its in-flight state; `create_optimistic(source)` overlays a signal with writes that revert when in-flight actions settle. See [Async and Loading](async-loading.md).
- `create_unique_id()` returns a stable unique string for `id`/`for`/`aria-*` wiring.
- `catch_error(fn, handler)` runs `fn` under a scope whose errors (now or from effects created inside) route to `handler`.
- `on_error(handler)` registers an error handler on the **current** scope; errors from child computations route to the nearest ancestor handler.

#### Reactive utilities

`untrack(fn)` runs `fn` without tracking any signal reads, which is
useful for reading a signal inside an effect without creating a dependency:

```python
from wybthon import create_effect, untrack

create_effect(lambda: print("a changed:", a(), "b is:", untrack(b)))
```

For explicit dependencies, use the **split effect** form. The first
function is the tracked compute stage; the second runs untracked with
the computed value (and, when it accepts a second parameter, the
previous value):

```python
from wybthon import create_effect

create_effect(count, lambda v: print("count is now", v))
create_effect(lambda: (a(), b()), lambda pair: print("changed:", pair))
create_effect(count, lambda v, prev: print(f"{prev} -> {v}"))
```

Because the apply stage is untracked, incidental signal reads inside it
can't over-subscribe the effect.

`merge_props(*sources)` merges multiple prop sources into a **reactive
proxy**.  Each source may be a plain dict or a callable getter (e.g., a
signal accessor that returns a dict).  Reads on the proxy are lazy:
when a source is callable, it's called on each property access, so
signal reads inside a reactive computation are tracked automatically.

```python
from wybthon import merge_props, create_signal

defaults = {"size": "md", "variant": "solid"}
final = merge_props(defaults, props)
final["size"]  # reads from props first, falls back to defaults

# Reactive source:
dyn, set_dyn = create_signal({"color": "red"})
merged = merge_props(defaults, dyn)
merged["color"]  # calls dyn() → reactive tracking
```

`split_props(props, *key_groups)` splits a props source by key name,
returning `(group1, group2, ..., rest)` as **reactive proxies**.

```python
from wybthon import split_props

local, rest = split_props(props, ["class", "style"])
# local["class"] lazily reads from props
```

#### Reactive list primitives

`map_array(source, map_fn, key=None)` creates a **keyed reactive list
mapping** with stable per-item scopes.  By default items are matched by
reference identity; pass `key=callable` to match by `key(item)` instead,
so a fresh object with the same key updates the existing scope in place.
The mapping callback runs **once** per unique item; when an item leaves,
its reactive scope is disposed.

```python
from wybthon import create_signal, map_array

items, set_items = create_signal(["A", "B", "C"])
mapped = map_array(items, lambda item, idx: f"{idx()}: {item()}")

mapped()                    # ["0: A", "1: B", "2: C"]
set_items(["B", "C", "D"])  # only "D" runs the mapping
```

`index_array(source, map_fn)` is similar but keyed by **index
position**.  Each slot has a reactive item signal that updates when the
value at that position changes.

```python
from wybthon import create_signal, index_array

items, set_items = create_signal(["A", "B", "C"])
mapped = index_array(items, lambda item, idx: f"[{idx}] {item()}")
# items[0] changes → slot 0's item signal fires
```

`create_selector(source)` creates an efficient **selection signal**.
Only computations that called `is_selected()` with the *previous* or
*new* key are notified, giving O(1) updates instead of O(n).

```python
from wybthon import create_signal, create_selector

selected, set_selected = create_signal(1)
is_selected = create_selector(selected)

is_selected(1)  # True
is_selected(2)  # False
set_selected(2)
# Only effects tracking key 1 and key 2 re-run
```

`create_root(fn)` runs `fn` in an independent reactive scope:

```python
from wybthon import create_root

result = create_root(lambda dispose: ...)
```

#### Automatic batching

Wybthon's scheduler batches automatically, matching SolidJS 2.0. There's
no `batch()` primitive; everything batches.

- **Writes apply immediately; effects are deferred.** Setting a signal
  updates its value right away: a read immediately after a write
  reflects the new value, and dependent memos recompute on their next
  read. Effects, however, don't run inline; they're scheduled and run
  on the next **flush**.
- **When the flush happens.** In the browser, a flush is scheduled on a
  microtask after the first write, and event handlers dispatched
  through Wybthon's event system flush automatically at the end of the
  handler. In plain Python scripts and tests, call `flush()` to settle
  effects deterministically.
- **Writes coalesce.** Any number of signal writes before a flush
  produce **one** run per affected effect. There's nothing to wrap in a
  batch; consecutive `set_a(1); set_b(2)` calls already coalesce.
- **Phases within a flush.** Render effects (internal holes and prop
  bindings, plus `create_render_effect`) run first, then the buffered
  DOM ops are committed across the Pyodide bridge in a single crossing,
  then user effects (`create_effect`) run. A user effect always
  observes the committed DOM, and an effect reading several memos
  derived from the same signal never observes an inconsistent,
  half-updated combination.
- **Memos are lazy (pull-based).** A `create_memo` recomputes only when
  it's *read* after one of its sources changed. A memo that's never
  read never runs, and several writes before the next read coalesce
  into a single recompute.
- **Equality short-circuits downstream work.** When a memo recomputes to a
  value equal to its previous one (per its `equals` policy), its consumers
  are *not* re-run. A `create_memo(lambda: n() > 0)` that stays `True` as `n`
  changes from `1` to `2` re-runs nothing downstream.
- **Deterministic order.** Within a flush, effects run in the order they
  were marked dirty. Effects enqueued while the graph settles (for
  example, by a user effect writing a signal) drain within the same
  flush, so one logical update fully settles before the flush returns.

```python
from wybthon import create_signal, create_effect, flush

a, set_a = create_signal(1)
b, set_b = create_signal(2)

create_effect(lambda: print("sum:", a() + b()))  # prints "sum: 3"

set_a(10)
set_b(20)
flush()  # prints "sum: 30" once, not twice
```

#### Ownership tree

Every reactive computation belongs to an **ownership tree** (inspired by
SolidJS).  Two base classes form the hierarchy:

- `Owner`: tracks child owners and cleanup callbacks.
- `Computation(Owner)`: a reactive computation that's also an ownership scope.

When a new effect or memo is created, it's automatically registered as a
child of `_current_owner`, the owner that's active at the time of
creation.  This forms a tree:

```
Root Owner
├── ComponentContext (MyApp)
│   ├── setup effect (on_mount callback)
│   ├── ComponentContext (Counter)
│   │   ├── setup effect (logger)
│   │   └── render effect
│   │       └── inner effect (conditionally created)
│   └── render effect
└── ...
```

**Disposal is depth-first:** when an owner is disposed, all its children
are disposed first, then its own cleanup callbacks run.  This guarantees
that inner scopes are torn down before outer ones.

**Async boundaries:** `await` drops the current reactive owner. Use
`get_owner()` before suspending and `run_with_owner(owner, fn)` when
scheduling work after `await` so effects and memos attach to the correct
scope (see [Reactivity API](../api/reactivity.md)).

When a `Computation` re-runs (due to a signal change), it disposes all
of its children and runs its own cleanups *before* re-executing its
function.  Any effects created during the new execution become fresh
children of the computation.  This prevents leaks from
conditionally-created effects.

##### Setup effects vs hole effects

The component body runs **once**.  Effects you create there are
*setup effects*, parented to the component context.  Effects created
inside a reactive hole (or returned by an inner `dynamic` expression)
are children of that hole's effect.

| Created during | Parent owner | Disposed when |
|----------------|--------------|---------------|
| **Setup** (component body, before `return`) | `_ComponentContext` | Component unmounts |
| **Reactive hole** (inside a hole getter or a child it created) | Hole's `Computation` | Next hole re-run or unmount |

Setup effects survive across hole re-runs because they aren't children
of any hole.  Effects created inside a hole are torn down every time
the hole re-runs (so their `on_cleanup` callbacks fire).

```python
from wybthon import component, create_effect, create_signal, dynamic, p

@component
def Timer(interval=1000):
    count, set_count = create_signal(0)

    # Setup effect: lives until the component unmounts
    create_effect(lambda: print("count is", count()))

    return p(
        # Hole effect: re-runs only when ``count`` changes; any inner
        # effects it creates are disposed before the next run.
        dynamic(lambda: f"Elapsed: {count()}"),
    )
```

#### Disposal

Calling `dispose()` on a computation unsubscribes it from every dependency and drops it as a source for its own observers; a disposed effect is skipped if it's still sitting in the current flush queue. Cleanup functions registered via `on_cleanup` inside effects are executed during disposal.

Disposing an `Owner` (or any subclass) walks the tree depth-first:
children are disposed before the owner's own cleanups run.  After
disposal, the owner is removed from its parent's children list.

#### Async memos

A memo whose body is an `async def` (or returns an awaitable) becomes
an **async computation**, a first-class citizen of the reactive graph:

```python
from wybthon import create_memo

async def fetch_user():
    resp = await js.fetch("/api/user")
    return await resp.json()

user = create_memo(fetch_user)
```

- **Reading before the first value raises `NotReadyError`.** A
  [`Loading`][wybthon.Loading] boundary turns that into fallback UI;
  reads through derived sync memos propagate the not-ready state, and
  effects that read a pending value suspend until it lands.
- **Stale-while-revalidate.** Once the memo has a value, later
  recomputes serve the previous value while the new one is in flight,
  so content stays visible during refreshes.
- **`is_pending(getter)`** is a tracked read that returns `True` while a
  recompute is in flight; use it to render inline refresh hints.
  **`latest(getter)`** reads without raising: it returns the stale value,
  or `None` before the first value.
- **Errors are stored and re-raised on read**, so a failed fetch hits
  the nearest [`ErrorBoundary`][wybthon.ErrorBoundary] when the memo is
  read during render.
- Signal reads inside the coroutine are tracked both before and after
  `await` points, so an async memo refetches when its dependencies
  change:

```python
from wybthon import create_signal, create_memo

version, set_version = create_signal(0)

async def fetch_todo():
    version()  # tracked: bump the version to refetch
    resp = await js.fetch(url)
    return await resp.json()

todo = create_memo(fetch_todo)
set_version(lambda v: v + 1)  # triggers a revalidation
```

See [Async and Loading](async-loading.md) for `Loading` boundaries,
lazy components, actions, and optimistic state.

## Next steps

- See [Lifecycle and Ownership](lifecycle.md) for the disposal model.
- Read [Async and Loading](async-loading.md) for async memos, loading boundaries, and actions.
- Browse the [`reactivity`][wybthon.reactivity] API reference.
