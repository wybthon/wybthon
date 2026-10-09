# Runtime contracts

Wybthon uses run-once component setup, explicit accessors, compiled templates, and a batched Virtual DOM. The VDOM collects mutations for the Python-to-JavaScript bridge. It doesn't choose reactive dependencies or require components to rerun.

The async API reference for this design is [Solid 2.0 RC.14's async data contract](https://github.com/solidjs/solid/blob/solid-js%402.0.0-rc.14/documentation/solid-2.0/05-async-data.md). This is a pinned prerelease reference, not a claim of complete Solid conformance. Wybthon retains Python equality, explicit accessor calls, ordinary `async def` actions, and real asyncio tasks.

## Read views

| Scope | Values and readiness | Publication |
| --- | --- | --- |
| Ordinary event or top-level read | Last published value | Matches visible UI |
| Tracked computation | Committed working values | Prepares a result; ordinary dependencies can hold its application |
| `latest(expression)` | Working values, or `None` before the first async result | Subscribes through an escape edge, so its own UI can publish during a hold |
| `is_pending(expression)` | Reports pending, held, affected, or optimistic state | Subscribes without holding its indicator |
| Action | Includes staged writes; functional setters compose on the newest value | Writes belong to that action's dependency group |
| `resolve(expression)` | Waits for fresh async dependencies, including quiet refreshes and cached memos | Returns a settled working result |
| `until(predicate)` | Same readiness rules, with optimistic edits hidden | Returns the settled truthy value |

A normal read wins when the same computation also reads a source through `latest` or `is_pending`. A computation that combines ordinary held data with a latest value still waits for its ordinary dependencies. An expression isn't an independent UI region merely because part of it calls `latest`.

Signal writes and successful store drafts stage values. Outside an action, `latest` doesn't expose writes that haven't been flushed. A microtask flush commits writes to the working graph. An ordinary bubbling event sends its matching route to Python and flushes after the handlers finish. `flush()` supplies an explicit synchronous boundary.

Store properties, length, membership, iteration, and snapshots select the same view, including properties first observed during a hold. New render consumers read the published version on their initial mount and subscribe to its eventual replacement.

## Independent transitions

An async recomputation holds publication only when an ordinary dependency path reaches a live publishing consumer. An unused memo or a pending-only indicator doesn't freeze the inputs. Initial loads use readiness and Loading fallbacks; quiet refreshes serve the previous value.

Each independent request starts its own transition. Its changed inputs and derived values stay on their published version until the requested data is ready. Unrelated writes can publish even when they occurred in the same microtask. Two separate detail panels can therefore finish in either order, while typing in a third panel continues normally.

Shared ordinary consumers join dependency groups. For example, an effect computing `(left(), right())` makes the two values publish consistently. Writes to the same signal or store entity, and action reads of another group's state, also join groups. Nested actions share their enclosing group. Once joined, a group remains joined until it publishes. These are publication groups, not database transactions with isolated reads or automatic rollback.

A newer request for the same reactive input supersedes the older task. The visible version stays unchanged until the replacement resolves. Removing the last publishing consumer releases its hold. An explicit `Loading(on=...)` boundary can choose fallback publication instead of retaining the old content.

## Ownership and rendering

Components own computations, nested roots, rows, and event tasks. `create_root(fn)` joins the current owner. Use `detached=True` only for a lifetime you'll dispose explicitly.

A split `create_effect(compute, apply)` tracks preparation and applies untracked after the DOM commit. Resources created during preparation belong to a provisional owner, allocated only when needed. A held replacement keeps the previous published owner's resources alive. Superseding a preparation disposes its provisional resources; publication replaces the old owner. Disposal releases both. Nested effects and `on_settled` callbacks also wait for preparation publication, and abandoned callbacks never run.

Cleanup returned by `apply`, or registered during it, belongs to that committed application. It runs before the next visible apply or on disposal. Render errors are also held with their dependencies, so a superseded speculative failure doesn't replace a valid visible error boundary.

`create_tracked_effect(fn)` combines tracking and side effects. Its cleanup runs before recomputation. Use split effects for resources that must follow visible state. Memo bodies still own their children for one computation run.

`For` owns mounted rows. Moves preserve row state, refs, and fragment ranges; removals dispose rows when their removal publishes. `Repeat` grows and shrinks integer slots directly. A changed keyed `Show` value creates a fresh branch scope. The scheduler prepares these changes, publishes ready render applications, commits buffered VDOM operations, and then runs user applications. Explicit DOM reads and refs can force a bridge commit.

## Async work

Async computations and event handlers run in real `asyncio.Task` instances. Reads after `await` remain tracked in computations. `asyncio.timeout` and `TaskGroup` work normally. Explicit child tasks don't inherit reactive tracking; use `TaskGroup` when the parent should cancel them.

Supersession, disposal, and cancellation of an action Future cancel suspended work and allow asynchronous `finally` cleanup. Cancellation remains cooperative. Version checks prevent an obsolete task's return value from publishing even if it suppresses cancellation.

`resolve` and `until` inspect readiness through arbitrary expressions and cached memo dependencies. Quiet refreshes are silent to `is_pending` but still block these awaiters. An async generator becomes ready at its first fresh yield; awaiting its value doesn't require the stream to end. Canceling an awaiter removes its temporary subscriptions and timeout.

Derived stores share memo readiness and errors. Their seed determines shape; an unresolved async projection is pending. Structural and field subscriptions preserve fine-grained updates after readiness has settled.

## Optimistic edits

Each optimistic edit belongs to the action that submitted it. Independent actions settle independently. Finishing, failing, or canceling one removes its edits and preserves other outstanding edits. Actions joined through shared dependencies remove their edits when the joined group publishes.

Scalar updater functions and store draft callbacks replay in submission order over the newest authoritative source. Replacement scalar writes replace the preceding value at their position in that order. For conflicting store edits, ordinary draft mutation order determines the result. This supports additive updates and disjoint edits without introducing a second conflict language.

Callbacks must be deterministic and free of external side effects because rebasing can run them again. Authoritative updates should arrive before the corresponding action completes. Failed optimistic edits disappear, but ordinary authoritative writes already made by an action aren't rolled back. Multiple draft edits from one action share a single removal and rebase.

`affects(signal_or_memo)` marks that value pending without starting a new fetch. `affects(store.child)` marks the selected subtree; sibling reads remain independent. Existing pending indicators update when the mark is added and removed. A whole-store mark applies to every descendant.

An optimistic edit made outside an action remains until the next transition adopts it. Prefer actions when an edit needs a clear lifetime.

## Python authoring

A component declares its inputs on a [`Props`][wybthon.Props] subclass and takes one parameter annotated with that class, or no parameters when it has no inputs. A `Prop[T]` field is reactive: reading `props.label` returns an accessor, whether the parent passed a value, an accessor, or a zero-argument function. Use `prop(default=...)` or `prop(default_factory=...)` for defaults, and `.peek()` for an intentional one-time read. Any other annotation declares a plain field, which returns the parent's latest value untracked. A plain field is never called by the read, so callbacks belong there. In dev mode (the default outside production builds), an unknown prop or a missing required one raises `TypeError` at the call site, including a template's `<{Component}>` tag. A component that can't receive new props (anything not mounted directly in a re-rendering hole's result or a render root) reads constant props without subscribing to anything; one that can is patched in place and its reads track one version signal per props instance. Both behave the same.

```python
from collections.abc import Callable

from wybthon import Prop, Props, component, html, prop


class SaveProps(Props):
    label: Prop[str] = prop(default="Save")
    on_save: Callable[[], None] | None = None


@component
def SaveButton(props: SaveProps):
    def save():
        if props.on_save is not None:
            props.on_save()  # the parent's callback, called only here

    return html(t"<button onclick={save}>{props.label}</button>")
```

DOM positions keep one accessor rule, in templates and element helpers alike: in children, attribute values, and bindings, an accessor or a function or bound method callable without required arguments is a reactive expression, and anything else is applied once. In a template, each reactive interpolation is its own binding, and an attribute built from several parts (`class="btn btn-{kind}"`) is one binding. A t-string passed to an element helper with a reactive interpolation is one reactive binding. A binding whose first run reads nothing reactive is dropped, keeping the DOM it produced. Event handlers and refs are never reactive, and a handler may take the event or no arguments. Python forbids a bare `lambda` inside a template interpolation, so wrap one in parentheses or give it a name. Component props don't use the arity rule; the declared field type decides. [`merge`][wybthon.merge] and [`omit`][wybthon.omit] return reactive mappings of accessors for spreading onto elements, and a key they don't supply reads as `None`.

## Diagnostics and limits

`diagnostics.inspect_transitions()` reports group IDs, pending computation IDs, action counts, held sources, queued applications, and affected targets. `inspect_graph(owner)` includes matching IDs, read modes, blockers, and prepared and published owners. These functions inspect metadata without evaluating values or joining groups. `runtime_stats()` includes transition and held-node counts.

The synchronous path creates no transition when there are no actions or async computations. Transition bookkeeping runs in Python; compiled template mounting, native teardown, delegated events, persistent store sequences, list edit journals, and batched kernel operations remain in use. General sequence splices and arbitrary replacements can still require linear work. Holding a group retains its published values and resources until completion or removal of demand.

The native concurrency benchmark, `python benchmarks/async_bench.py`, checks independent publication at increasing widths. Browser collection benchmarks separately guard synchronous work counts and bridge costs. Neither is a claim of parity with a JavaScript framework's benchmark scores.
