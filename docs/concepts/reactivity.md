### Reactivity

Signals drive the render pipeline.

```python
from wybthon import create_signal, create_effect, create_memo, batch

count, set_count = create_signal(0)
double = create_memo(lambda: count() * 2)

create_effect(lambda: print("double:", double()))
set_count(1)
```

- `create_signal(value, *, equals=...)` returns a `(getter, setter)` tuple.
  The setter accepts either a new value or an **updater function**
  (`set_count(lambda n: n + 1)`). By default `equals` uses **value
  equality** (`==`) with an identity fast-path; pass `equals=False` to
  fire on every set, or a custom comparator (e.g.,
  `equals=lambda a, b: a is b` for SolidJS-style identity-only
  semantics). See [Reactivity API](../api/reactivity.md).
- `create_memo(fn)` returns a derived getter; recomputes **lazily** on read after a dependency changes.
- `create_effect(fn)` runs and re-runs on dependencies; supports previous value.
- `create_render_effect(fn)` is like `create_effect` but runs in the **render phase**, before user effects (the framework's own DOM bindings live here).
- `create_computed(fn)` runs eagerly in the render phase; use it to push derived state into another signal.
- `batch()` batches updates as a context manager, or `batch(fn)` with callback.
- `create_resource(fetcher)` returns an async data primitive with loading/error state.
- `create_deferred(source)` returns a getter that trails `source` by one event-loop tick, decoupling expensive consumers from rapid updates.
- `create_unique_id()` returns a stable unique string for `id`/`for`/`aria-*` wiring.
- `catch_error(fn, handler)` runs `fn` under a scope whose errors (now or from effects created inside) route to `handler`.

#### Reactive utilities

`untrack(fn)` runs `fn` without tracking any signal reads, which is
useful for reading a signal inside an effect without creating a dependency:

```python
from wybthon import create_effect, untrack

create_effect(lambda: print("a changed:", a(), "b is:", untrack(b)))
```

`on(deps, fn, defer=False)` creates an effect with explicit dependency
tracking.  The body of `fn` is automatically untracked:

```python
from wybthon import on

on(count, lambda v: print("count is now", v))
on([a, b], lambda va, vb: print(f"a={va}, b={vb}"), defer=True)
```

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

`map_array(source, map_fn)` creates a **keyed reactive list mapping**
with stable per-item scopes.  Items are matched by reference identity.
The mapping callback runs **once** per unique item; when an item leaves,
its reactive scope is disposed.

```python
from wybthon import create_signal, map_array, create_effect

items, set_items = create_signal(["A", "B", "C"])
mapped = map_array(items, lambda item, idx: f"{idx()}: {item()}")

create_effect(lambda: print(mapped()))  # ["0: A", "1: B", "2: C"]
set_items(["B", "C", "D"])             # only "D" runs the mapping
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

#### Scheduling semantics

Wybthon's scheduler is **synchronous and glitch-free**, matching SolidJS's
observable behavior:

- **Writes propagate synchronously.** Outside a `batch`, setting a signal
  updates dependent memos and runs affected effects *before the setter
  returns*. There's no microtask delay, and there's nothing to `await` or
  sleep on: a read immediately after a write reflects the new value.
- **Two phases per update.** A write first marks the graph stale (the "pure"
  phase), then effects run (the "effect" phase) and *pull* their
  dependencies. Because effects pull a fully-settled graph, an effect reading
  several memos derived from the same signal never observes an inconsistent,
  half-updated combination, and it runs **once** per logical change rather
  than once per intermediate edge.
- **Memos are lazy (pull-based).** A `create_memo` recomputes only when it's
  *read* after one of its sources changed. A memo that's never read never
  runs, and several writes before the next read coalesce into a single
  recompute.
- **Equality short-circuits downstream work.** When a memo recomputes to a
  value equal to its previous one (per its `equals` policy), its consumers
  are *not* re-run. A `create_memo(lambda: n() > 0)` that stays `True` as `n`
  changes from `1` to `2` re-runs nothing downstream.
- **Deterministic order.** Effects run in the order they were first marked
  dirty (subscription order for a shared source). Effects enqueued while the
  graph settles are drained within the same flush, so one logical update
  fully settles before control returns.

`batch()` defers the effect phase until the outermost batch exits, coalescing
many writes into a single flush. It works as a context manager or with a
callback:

```python
# Context manager (Pythonic)
with batch():
    set_a(1)
    set_b(2)

# Callback (SolidJS-style)
batch(lambda: (set_a(1), set_b(2)))
```

Both forms flush dependent effects synchronously when the batch exits.

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

#### Resources, cancellation, and Suspense

`create_resource(fetcher)` creates a `Resource`, a callable accessor with tracked `loading`, `error`, `latest`, and `state` properties. Calling `refetch()` starts a new fetch. Calling `cancel()` aborts any in-flight JS fetch (via `AbortController` when available), cancels the Python task, invalidates the current version to ignore late results, and resets `loading`. `mutate(value)` writes the data directly for optimistic updates.

You can also pass a source signal to automatically refetch when it changes:

```python
from wybthon import create_resource, create_signal

user_id, set_user_id = create_signal(1)

async def load_user(uid, signal=None):
    resp = await fetch(f"/api/users/{uid}")
    return await resp.json()

res = create_resource(user_id, load_user)
# Changing user_id will automatically refetch
```

To render a loading UI declaratively, wrap the UI in `Suspense`. Reading a pending resource inside the boundary registers it automatically; no manual wiring is needed:

```python
from wybthon import Suspense, h, create_resource

async def load_user(signal=None):
    # ... fetch user ...
    return {"name": "Ada"}

res = create_resource(load_user)

view = Suspense(
    fallback=h("p", {}, "Loading user..."),
    children=lambda: h("pre", {}, lambda: str(res())),
)
```

- Refetches (`state == "refreshing"`) don't re-trigger `Suspense`; the previous data stays readable through the accessor and `latest`, matching SolidJS.

## Next steps

- See [Lifecycle and Ownership](lifecycle.md) for the disposal model.
- Read [Suspense and Lazy Loading](suspense-lazy.md) for resource UI patterns.
- Browse the [`reactivity`][wybthon.reactivity] API reference.
