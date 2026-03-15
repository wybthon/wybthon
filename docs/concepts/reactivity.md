### Reactivity

Signals drive the render pipeline.

```python
from wybthon import signal, computed, effect, batch

count = signal(0)
double = computed(lambda: count.get() * 2)

def log():
    print("double:", double.get())

eff = effect(log)
count.set(1)
```

- `signal(value)` → get/set
- `computed(fn)` → derived; dispose when not needed
- `effect(fn)` → runs and re-runs on dependencies
- `batch()` → batch updates and schedule once
- `create_resource(fetcher)` → async data with loading/error signals

#### Signals-first API (recommended)

For use inside `@component` functions, prefer the signals-first API:

```python
from wybthon import create_signal, create_effect, create_memo

count, set_count = create_signal(0)
double = create_memo(lambda: count() * 2)
create_effect(lambda: print("count changed:", count()))
```

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

`batch()` coalesces multiple `set()` operations into a single flush at the end of the batch.

#### Disposal

Calling `dispose()` on a computation cancels its subscriptions and removes any pending re-runs from the queue. Cleanup functions registered via `on_effect_cleanup` are executed during disposal.

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
