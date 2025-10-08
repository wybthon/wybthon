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
- `use_resource(fetcher)` → async data with loading/error signals

#### Scheduling semantics

Effects are scheduled on a microtask in Pyodide via `queueMicrotask` when available, with fallbacks to `setTimeout(0)` and a pure-Python timer in non-browser environments. Wybthon guarantees deterministic FIFO ordering for effect re-runs: subscribers are notified in subscription order, and any updates scheduled during a flush are deferred to the next microtask to avoid reentrancy.

`batch()` coalesces multiple `set()` operations into a single flush at the end of the batch.

#### Disposal

Calling `dispose()` on a computation cancels its subscriptions and removes any pending re-runs from the queue. Cleanup functions registered via `on_effect_cleanup` are executed during disposal.

#### Resources, cancellation, and Suspense

`use_resource(fetcher)` creates a `Resource` with `data`, `error`, and `loading` signals. Calling `reload()` starts a new fetch and sets `loading=True`. Calling `cancel()` aborts any in-flight JS fetch (via `AbortController` when available), cancels the Python task, invalidates the current version to ignore late results, and sets `loading=False`.

To render a loading UI declaratively, wrap UI with `Suspense` and pass a `resource` (or `resources=[...]`) and a `fallback`:

```python
from wybthon import Suspense, h, use_resource

async def load_user(signal=None):
    # ... fetch user ...
    return {"name": "Ada"}

res = use_resource(load_user)

view = h(
    Suspense,
    {"resource": res, "fallback": h("p", {}, "Loading user...")},
    h("pre", {}, lambda p: str(res.data.get())),
)
```

- Pass `keep_previous=True` to keep previously rendered children visible during subsequent reloads while still showing new data once ready.
