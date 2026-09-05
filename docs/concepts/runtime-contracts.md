# Runtime contracts

Wybthon uses run-once component setup, explicit accessors, and a batched Virtual DOM. The VDOM is the rendering implementation; it doesn't change which reactive reads subscribe to which computations.

## Reads and writes

Signal writes and successful store drafts stage a working version. Ordinary reads outside a computation keep seeing the last revealed version until the scheduler commits. This applies to properties you haven't read before, list length, membership, iteration, and snapshots. Observation history never chooses the version.

Tracked computation reads see the working graph. During an async transition, computations can prepare new values while the visible DOM and ordinary reads keep their previous version. `latest(accessor)` deliberately reads the working value. An action reads its own staged writes. `is_pending(accessor)` observes readiness without turning an ordinary read of the same source into a pending-only read.

A microtask flush batches writes. An ordinary bubbling event sends its whole matching route to Python and flushes once after the handlers finish. `flush()` is useful in native tests and for explicit synchronous boundaries.

## Ownership and resources

Components own their computations, nested roots, list rows, and event tasks. `create_root(fn)` joins the current owner. Use `detached=True` only when you intend to manage a separate lifetime, and retain its disposer.

A split `create_effect(compute, apply)` tracks `compute` and runs `apply` untracked after the DOM commit. Cleanup returned by `apply`, or registered during `apply`, belongs to that committed application. It runs before the next visible apply or when the effect is disposed. Preparing a held replacement doesn't tear down a resource that still belongs to the visible UI.

`create_tracked_effect(fn)` explicitly combines tracking and side effects. Its `on_cleanup` callbacks run before recomputation. Use split effects for subscriptions, listeners, and other resources that must follow visible state.

`create_memo` evaluates initially unless `lazy=True`. A lazy memo suspends when its last observer leaves: its work, dependencies, and tasks are released. A later read starts it again. Explicit disposal is permanent.

`For` owns mounted rows. Entity moves preserve row state, refs, and fragment ranges. Removed rows are disposed when their removal becomes visible. `Repeat` grows and shrinks integer slots directly. A changed keyed `Show` value creates a new branch scope, including same-type child components.

## Async work

Async computations and event handlers run in real `asyncio.Task` instances. Dependencies read after an `await` remain tracked in computations. Ordinary `asyncio.timeout` and `TaskGroup` work inside them. Child tasks created explicitly with `asyncio.create_task` have their own ordinary asyncio lifetime; use `TaskGroup` when the parent should cancel them.

A changed computation input cancels the superseded task. Disposal and action Future cancellation cancel suspended work and allow asynchronous `finally` cleanup. Cancellation is cooperative: a coroutine that blocks Python or suppresses cancellation can't be forcibly stopped. `resolve` and `until` release their temporary subscriptions when their caller is canceled.

Derived stores use the same readiness, errors, Loading boundaries, and `refresh` behavior as memos. Their seed determines shape; an unresolved async projection still reports pending. Async generators publish each yielded projection and close when their owner is disposed.

## Actions and optimistic stores

Overlapping actions join the scheduler's current transition. Their ordinary writes reveal together when its work settles. This is one shared transaction, not independent per-action isolation.

Optimistic stores replay draft edits in submission order over the latest authoritative source. All overlays in the transition are removed when it settles, including failure or cancellation. Authoritative updates must therefore arrive before the corresponding action completes. Overlay callbacks must be deterministic and free of external side effects because rebasing can run them again.

`until(predicate)` reads authoritative state, so an optimistic edit can't acknowledge itself. Ordinary UI reads see the optimistic overlay. `refresh` requests a quiet recomputation and returns an awaitable for completion; quiet refresh doesn't show a pending indicator.

## Collection and memory limits

Store lists use structurally shared sequence versions. Append and indexed updates avoid copying the entire sequence; a general splice can rebuild it. Mounted `For` regions consume recent edit records to handle local changes without mapping every existing row. Arbitrary replacement arrays use keyed matching and the generic VDOM diff. Removal still updates subsequent index accessors when indices change.

Template prototypes use a bounded cache of 256 entries. Varying instance attributes don't create a template per instance. Node handles, listeners, and refs are released on unmount; selector-based root adoption is canonical. The diagnostic APIs expose registry and operation counts for regression tests.
