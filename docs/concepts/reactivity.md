### Reactivity

Signals drive the render pipeline.

```python
from wybthon import create_signal, create_effect, create_memo, batch

count, set_count = create_signal(0)
double = create_memo(lambda: count() * 2)

create_effect(lambda: print("double:", double()))
set_count(1)
```

- `create_signal(value)` → `(getter, setter)` tuple
- `create_memo(fn)` → derived getter; re-computes only when deps change
- `create_effect(fn)` → runs and re-runs on dependencies; supports previous value
- `batch()` → batch updates as context manager or `batch(fn)` with callback
- `create_resource(fetcher)` → async data with loading/error signals

#### Reactive utilities

`untrack(fn)` runs `fn` without tracking any signal reads — useful for
reading a signal inside an effect without creating a dependency:

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

`merge_props(*sources)` merges multiple prop dicts (later sources win):

```python
from wybthon import merge_props

defaults = {"size": "md", "variant": "solid"}
final = merge_props(defaults, props)
```

`split_props(props, *key_groups)` splits a props dict by key name,
returning `(group1, group2, ..., rest)`:

```python
from wybthon import split_props

local, rest = split_props(props, ["class", "style"])
```

`create_root(fn)` runs `fn` in an independent reactive scope:

```python
from wybthon import create_root

result = create_root(lambda dispose: ...)
```

#### Scheduling semantics

Effects are scheduled on a microtask in Pyodide via `queueMicrotask` when available, with fallbacks to `setTimeout(0)` and a pure-Python timer in non-browser environments. Wybthon guarantees deterministic FIFO ordering for effect re-runs: subscribers are notified in subscription order, and any updates scheduled during a flush are deferred to the next microtask to avoid reentrancy.

`batch()` coalesces multiple setter operations into a single flush at the end of the batch. It can be used as a context manager or with a callback:

```python
# Context manager (Pythonic)
with batch():
    set_a(1)
    set_b(2)

# Callback (SolidJS-style) — effects flush synchronously before returning
batch(lambda: (set_a(1), set_b(2)))
```

#### Ownership tree

Every reactive computation belongs to an **ownership tree** (inspired by
SolidJS).  Two base classes form the hierarchy:

- `Owner` — tracks child owners and cleanup callbacks.
- `Computation(Owner)` — a reactive computation that is also an ownership scope.

When a new effect or memo is created, it is automatically registered as a
child of `_current_owner`, the owner that is active at the time of
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

When a `Computation` re-runs (due to a signal change), it disposes all
of its children and runs its own cleanups *before* re-executing its
function.  Any effects created during the new execution become fresh
children of the computation.  This prevents leaks from
conditionally-created effects.

##### Setup effects vs render effects

Inside a component, effects have different lifetimes depending on
**when** they are created:

| Created during | Parent owner | Disposed when |
|----------------|--------------|---------------|
| **Setup** (component body, before `return`) | `_ComponentContext` | Component unmounts |
| **Render** (inside the render function) | Render `Computation` | Next re-render or unmount |

Setup effects survive re-renders because they are children of the
component context, not the render effect.  Render effects are torn down
every time the render function re-runs.

```python
@component
def Timer(interval: int = 1000):
    count, set_count = create_signal(0)

    # Setup effect — lives until the component unmounts
    create_effect(lambda: print("count is", count()))

    def render():
        # Render effect — disposed and recreated on each re-render
        create_effect(lambda: print("rendered with", count()))
        return p(f"Elapsed: {count()}")

    return render
```

#### Disposal

Calling `dispose()` on a computation cancels its subscriptions and removes any pending re-runs from the queue. Cleanup functions registered via `on_cleanup` inside effects are executed during disposal.

Disposing an `Owner` (or any subclass) walks the tree depth-first:
children are disposed before the owner's own cleanups run.  After
disposal, the owner is removed from its parent's children list.

#### Resources, cancellation, and Suspense

`create_resource(fetcher)` creates a `Resource` with `data`, `error`, and `loading` signals. Calling `reload()` starts a new fetch and sets `loading=True`. Calling `cancel()` aborts any in-flight JS fetch (via `AbortController` when available), cancels the Python task, invalidates the current version to ignore late results, and sets `loading=False`.

You can also pass a source signal to automatically refetch when it changes:

```python
from wybthon import create_resource, create_signal

user_id, set_user_id = create_signal(1)

async def load_user(signal=None):
    resp = await fetch(f"/api/users/{user_id()}")
    return await resp.json()

res = create_resource(user_id, load_user)
# Changing user_id will automatically refetch
```

To render a loading UI declaratively, wrap UI with `Suspense` and pass a `resource` (or `resources=[...]`) and a `fallback`:

```python
from wybthon import Suspense, h, create_resource

async def load_user(signal=None):
    # ... fetch user ...
    return {"name": "Ada"}

res = create_resource(load_user)

view = h(
    Suspense,
    {"resource": res, "fallback": h("p", {}, "Loading user...")},
    h("pre", {}, lambda p: str(res.data.get())),
)
```

- Pass `keep_previous=True` to keep previously rendered children visible during subsequent reloads while still showing new data once ready.
