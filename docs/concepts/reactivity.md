# Reactivity

Signals drive the render pipeline. This page explains how the graph
schedules work: staged writes, the flush and its phases, lazy memos,
deferred effects, dev-mode diagnostics, and the ownership tree.
[Primitives](primitives.md) is the per-function reference.

```python
from wybthon import create_effect, create_memo, create_signal, flush

count, set_count = create_signal(0)
double = create_memo(lambda: count() * 2)

create_effect(double, lambda value: print("double:", value))
flush()          # prints "double: 0" (the first run is deferred to a flush)
set_count(1)
double()         # still 0: the write is staged
flush()          # prints "double: 2"
```

In the browser the flush happens automatically, so application code
rarely calls [`flush`][wybthon.flush]. In CPython tests, call it after
writes.

## Staged writes and flush timing

Wybthon's scheduler matches SolidJS 2.0. There is no `batch()`; every
write batches.

- **Writes are staged, not applied.** `set_count(1)` records a pending value. `count()` keeps returning the committed value until the graph flushes. Functional updates (`set_count(lambda n: n + 1)`) receive the latest *staged* value, so consecutive updates compose.
- **When the flush happens.** In the browser, the first write schedules a flush on a microtask, and event handlers dispatched through Wybthon flush when they return. In plain Python, call `flush()`.
- **Writes coalesce.** Any number of writes before a flush produce one run per affected effect and one DOM commit.
- **Equality short-circuits.** A write equal to the committed value (under the signal's `equals`) is dropped at commit time and notifies nothing.

```python
from wybthon import create_effect, create_signal, flush

a, set_a = create_signal(1)
b, set_b = create_signal(2)

create_effect(lambda: a() + b(), lambda total: print("sum:", total))
flush()     # sum: 3

set_a(10)
set_b(20)
flush()     # sum: 30, printed once
```

### The three phases of a flush

1. **Render phase.** Staged writes commit and their observers are marked dirty. Render effects (holes, reactive prop bindings, and [`create_render_effect`][wybthon.create_render_effect]) run and emit DOM operations into the kernel's buffer.
2. **DOM commit.** The buffered operations cross the Pyodide bridge once and the JS kernel applies them.
3. **Effect phase.** User effects ([`create_effect`][wybthon.create_effect]) run and observe the committed DOM.

Writes made during any phase loop the phases until the graph settles,
so one logical update finishes before the flush returns. Callbacks
registered with [`on_settled`][wybthon.on_settled] run after that.
A runaway loop (an effect writing its own dependency forever) raises
`RuntimeError` after a bounded number of rounds.

### Memos are lazy and glitch-free

A memo recomputes only when it's *read* after a source changed. Several
writes before the next read coalesce into one recompute, and a memo
nobody reads never runs. Reading a memo pulls its sources current first,
so a diamond (`total` reads `left` and `right`, which both read `n`)
never observes one updated side and one stale side. When the recomputed
value is unchanged under `equals`, downstream computations aren't re-run.

### Effects start after mount

The first run of a `create_effect` is deferred to the effect phase of
the next flush. Inside a component that means the effect sees the
mounted DOM on its first run, and refs are already assigned. Render
effects, by contrast, run immediately at creation.

## Reading without tracking

[`untrack`][wybthon.untrack] runs a function with tracking suppressed;
every accessor's `.peek()` does the same for a single read:

```python
from wybthon import create_effect, untrack

create_effect(lambda: (a(), untrack(b)), lambda pair: print("a changed:", pair))
seed = initial.peek()
```

For explicit dependencies prefer the **split effect**: the compute stage
tracks, and the apply stage runs untracked with the computed value (and
the previous one when it declares two parameters):

```python
create_effect(count, lambda v: print("count is now", v))
create_effect(lambda: (a(), b()), lambda pair: print("changed:", pair))
create_effect(count, lambda v, prev: print(f"{prev} -> {v}"))
```

Because `apply` is untracked, incidental reads inside it never
over-subscribe the effect, and signal writes are allowed there.

## Dev-mode diagnostics

With [`DEV_MODE`][wybthon.DEV_MODE] on (the default; see
[`set_dev_mode`][wybthon.set_dev_mode]), the graph enforces two rules:

- **No writes inside tracking scopes.** Writing a signal or store from a memo body, a single-function effect, or a hole raises [`WriteInScopeError`][wybthon.WriteInScopeError]. Derive the value with a memo, or move the write into the `apply` stage of a split effect, an event handler, or an [`action`][wybthon.action].
- **No untracked reads at the top level of a component body.** Calling a signal, memo, or prop there freezes the value and warns once per component and value. Read it in a hole, memo, or effect, or make the one-time read explicit with `.peek()` or `untrack`.

```python
from wybthon import create_effect, create_memo, create_signal

count, set_count = create_signal(0)
log, set_log = create_signal([])

# Raises WriteInScopeError in dev mode as soon as the memo runs:
bad = create_memo(lambda: set_log(lambda l: l + [count()]))

# Fine: the write lives in the untracked apply stage.
create_effect(count, lambda n: set_log(lambda l: l + [n]))
```

## Reactive list primitives

[`map_array`][wybthon.map_array] maps a reactive list to rows with a
stable scope per row; `keyed=True` (identity, the default), `False`
(position), or a key function selects the matching strategy and the
callback shape. [`create_selector`][wybthon.create_selector] turns a
selection signal into `is_selected(key)` so only the affected rows
update. See [Primitives](primitives.md#map_array) for the shapes.

## Ownership tree

Every computation belongs to an **ownership tree**:

- [`Owner`][wybthon.Owner] tracks child owners, cleanup callbacks, context values, and an optional error handler.
- [`Computation`][wybthon.Computation] is an `Owner` that also tracks sources; memos and effects are computations.

A new effect or memo registers as a child of the owner active at
creation time. Component instances, holes, `For` rows, and
[`create_root`][wybthon.create_root] roots are owners too:

```
Root owner (render)
├── Component (App)
│   ├── effect (created in the body)
│   ├── Component (Counter)
│   │   ├── memo
│   │   └── hole scope
│   │       └── render effect
│   └── hole scope
│       └── render effect
│           └── effect (created inside the hole's subtree)
└── ...
```

**Disposal is depth-first:** children are disposed first, then the
owner's cleanups run in LIFO order, then it detaches from its parent.
When a computation re-runs it disposes its children and runs its
cleanups *before* re-executing, so conditionally created effects never
leak.

**Async boundaries.** `await` drops the active owner. Capture it with
[`get_owner`][wybthon.get_owner] and restore it with
[`run_with_owner`][wybthon.run_with_owner] when creating primitives
after the boundary. Async memos and async effects handle this for you:
every resume after an `await` runs as the same computation, and reads
after the `await` are tracked exactly like reads before it.

### Body effects versus hole effects

| Created during | Parent owner | Disposed when |
| --- | --- | --- |
| Component body | the component's scope | the component unmounts |
| A hole's expression or the subtree it mounted | the hole's scope | the hole re-evaluates or unmounts |
| A `For` row | the row's owner | the row leaves the list |

```python
from wybthon import Prop, component, create_effect, create_signal, prop
from wybthon.html import p


@component
def Timer(interval: Prop[int] = prop(1000)):
    count, set_count = create_signal(0)

    # Body effect: lives until the component unmounts.
    create_effect(count, lambda n: print("count is", n))

    # Hole: re-runs only when count changes.
    return p(lambda: f"Elapsed: {count()}")
```

## Disposal

Calling `.dispose()` on a computation unsubscribes it from every source
and drops it as a source for its own observers; a disposed effect
sitting in the current flush queue is skipped. Disposing a
[`Root`][wybthon.Root] returned by [`render`][wybthon.render] unmounts
the tree, disposes every scope under it, and unregisters the container
as an event root.

## Async memos

A memo whose body is `async def` (or returns an awaitable, or is an
async generator) becomes an **async computation**, a first-class node
in the graph:

```python
from wybthon import create_memo, create_signal

user_id, set_user_id = create_signal(1)


async def load_user():
    uid = user_id()                       # tracked: refetches when it changes
    return await fetch_json(f"/api/users/{uid}")


user = create_memo(load_user)
```

- **Reading before the first value raises [`NotReadyError`][wybthon.NotReadyError].** The nearest [`Loading`][wybthon.Loading] boundary turns that into fallback UI; sync memos that read a pending value become pending themselves; a hole that hits it keeps its previous content.
- **Stale-while-revalidate.** Once the memo has a value, recomputes serve the previous value while the new one is in flight.
- **[`is_pending`][wybthon.is_pending]** is a tracked probe that's `True` while a change-triggered recompute is in flight; **[`latest`][wybthon.latest]** reads without ever raising; **[`resolve`][wybthon.resolve]** awaits the next settled value; **[`refresh`][wybthon.refresh]** recomputes quietly.
- **Errors are stored and re-raised on read**, so a failed fetch reaches the nearest [`Errored`][wybthon.Errored] boundary.

See [Async and loading](async-loading.md) for boundaries, actions, and
optimistic state.

## Next steps

- See [Lifecycle and ownership](lifecycle.md) for the disposal model in detail.
- Read [Async and loading](async-loading.md) for async memos, `Loading`, and actions.
- Browse the [`reactivity`](../api/reactivity.md) API reference.
