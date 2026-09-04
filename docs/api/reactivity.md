### wybthon.reactivity

::: wybthon.reactivity

#### What's in this module

`wybthon.reactivity` is the pure-Python reactive graph: signals, memos,
effects, ownership, the scheduler, async computations, actions, and the
props utilities that components are built on. Nothing here touches the
DOM, so everything works in CPython as well as Pyodide. Import from
`wybthon` in application code; the `_core`, `_primitives`, `_actions`,
`_list`, and `_props` submodules are implementation detail.

Three rules shape every API here. Writes are **staged**: a setter records
a value, and reads keep returning the committed value until the next
flush (a microtask, the end of an event handler, or an explicit
[`flush`][wybthon.flush]). Effects are **deferred**: `create_effect`
runs for the first time on the next flush, after the DOM has been
committed, not at creation. Async work runs in **transitions**: when a
change makes an async memo recompute, the UI that depends on the change
holds on the old state until the new value lands, and an
[`action`][wybthon.action]'s writes reveal together when it settles.

#### Typed core

| Name | Description |
| --- | --- |
| [`Accessor`][wybthon.Accessor] | Zero-arg callable returning a reactive value; `.peek()` reads untracked. |
| [`Setter`][wybthon.Setter] | Protocol for the write half of a signal; accepts a value or an updater. |
| [`Signal`][wybthon.Signal] | Mutable container behind `create_signal`; the getter is a `Signal`. |
| [`Memo`][wybthon.Memo] | Read-only derived value returned by `create_memo`. |
| [`Prop`][wybthon.Prop] | Accessor for one component parameter; unwraps accessors the parent passed. |
| [`Props`][wybthon.Props] | Read-only mapping of prop name to `Prop`. |
| [`Owner`][wybthon.Owner] | Ownership scope; disposing it disposes children and runs cleanups. |
| [`Computation`][wybthon.Computation] | Tracked function node behind memos and effects; `.dispose()` stops it. |
| [`Action`][wybthon.Action] | Wrapped mutation returned by `action`; `.pending` is a tracked accessor. |
| [`Transition`][wybthon.Transition] | The open transaction holding in-flight changes (exposed for tooling; no public methods). |
| [`NotReadyError`][wybthon.NotReadyError] | Raised when reading an async computation that has no value yet. |
| [`WriteInScopeError`][wybthon.WriteInScopeError] | Raised in dev mode when a signal or store is written inside a tracking scope. |

#### Primitives

| Name | Description |
| --- | --- |
| [`create_signal`][wybthon.create_signal] | `(getter, setter)` pair; `equals=` policy; function form makes a writable derived signal. |
| [`create_memo`][wybthon.create_memo] | Lazy, glitch-free derived value; `async def` bodies become async computations; `loading_value=` serves a value before the first run lands. |
| [`create_effect`][wybthon.create_effect] | Side effect after DOM commit; split `(compute, apply)` form recommended. |
| [`create_render_effect`][wybthon.create_render_effect] | Effect in the render phase, before the DOM commit; first run is immediate. |
| [`on_settled`][wybthon.on_settled] | Run once after the flush that mounted the component; may return a cleanup. |
| [`on_cleanup`][wybthon.on_cleanup] | Register a cleanup on the active scope. |
| [`create_root`][wybthon.create_root] | Independent ownership root; `fn(dispose)`. |
| [`flush`][wybthon.flush] | Apply staged writes, run dirty effects, commit the DOM now. |
| [`untrack`][wybthon.untrack] | Run a function without tracking its reads. |
| [`get_owner`][wybthon.get_owner], [`run_with_owner`][wybthon.run_with_owner] | Capture the owner before an `await` and restore it after. |
| [`get_observer`][wybthon.get_observer] | The computation currently tracking reads, or `None`. |
| [`is_pending`][wybthon.is_pending] | Tracked probe: `True` while what `fn` reads is held by a transition, recomputing, declared with `affects`, or optimistically overridden. |
| [`latest`][wybthon.latest] | Evaluate against the newest state: held values return the value being computed; not-ready reads return the stale value or `None`. |
| [`refresh`][wybthon.refresh] | Quietly recompute a memo or derived store; returns an awaitable. Inside an action, lands with the action. |
| [`resolve`][wybthon.resolve] | Awaitable for the next settled value of an expression. |
| [`action`][wybthon.action] | Wrap a mutation in a transaction: its writes reveal together when it settles. |
| [`create_optimistic`][wybthon.create_optimistic] | Value override that reveals now and reverts when the action settles. |
| [`affects`][wybthon.affects] | Inside an action, mark values as pending before they're written. |
| [`until`][wybthon.until] | Awaitable for a predicate to become truthy on the authoritative (non-optimistic) view. |
| [`prop`][wybthon.prop] | Declare a typed component parameter default. |
| [`merge`][wybthon.merge], [`omit`][wybthon.omit] | Reactive prop-mapping views (later sources win; drop keys). |
| [`children`][wybthon.children] | Memo flattening a children getter into a list. |
| [`map_array`][wybthon.map_array] | Reactive list mapping with per-row scopes; the engine behind `For`. |
| [`create_selector`][wybthon.create_selector] | `is_selected(key)` that notifies only the affected rows. |
| [`create_unique_id`][wybthon.create_unique_id] | Process-unique id string for `id`/`for` pairs. |
| [`is_accessor`][wybthon.is_accessor] | `True` for an `Accessor` or a zero-arg function. |

#### Idioms

```python
from wybthon import create_effect, create_memo, create_signal, flush

count, set_count = create_signal(0)
doubled = create_memo(lambda: count() * 2)

create_effect(doubled, lambda value, prev: print(prev, "->", value))

set_count(lambda n: n + 1)
count()   # 0: the write is staged
flush()   # commits the write, runs the effect: prints "None -> 2"
count()   # 1
```

Async data is an ordinary memo with an `async def` body. Reads before
the first value raise `NotReadyError`, which the nearest
[`Loading`][wybthon.Loading] boundary turns into fallback UI; later
recomputes open a transition that holds the dependent UI on the old
state until the new value lands.

```python
from wybthon import action, create_memo, create_optimistic, is_pending, refresh, span

async def load_likes():
    return await fetch_like_count()

likes = create_memo(load_likes)
shown, set_shown = create_optimistic(likes)

@action
async def like():
    set_shown(lambda n: (n or 0) + 1)
    await api_like()
    await refresh(likes)

hint = span(lambda: "Refreshing..." if is_pending(likes) else "")
```

Internally, two module globals (the active owner and the active
observer) drive tracking and ownership; `get_owner()` and
`get_observer()` expose them read-only.

#### See also

- [Concepts: Reactivity](../concepts/reactivity.md)
- [Concepts: Primitives](../concepts/primitives.md)
- [Concepts: Lifecycle and ownership](../concepts/lifecycle.md)
- [Concepts: Async and loading](../concepts/async-loading.md)
- [Guides: Testing](../guides/testing.md) (driving flushes in CPython)
- [Guides: Typing](../guides/typing.md)
