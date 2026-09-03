"""The reactive graph: accessors, signals, computations, and the scheduler.

This module is the hot core of Wybthon's reactivity and is deliberately
self-contained: every piece of state the read and write paths touch is
a module-level global here, so `Signal.__call__` and
`Computation._update` never pay for cross-module attribute lookups.

Semantics (matching SolidJS 2.0):

- **Writes are staged, not applied.** `set_count(1)` records a pending
  value; `count()` keeps returning the committed value until the next
  flush (a browser microtask, the end of an event handler, or an
  explicit [`flush`][wybthon.flush]). There is no `batch()`; every
  write batches.
- **The graph is glitch-free and pull-based.** Memos recompute only
  when read after a source changed, and skip notifying their observers
  when the recomputed value is unchanged.
- **Async is part of the graph.** A computation whose body is
  `async def` (or an async generator) becomes an *async computation*:
  reading it before its first value raises
  [`NotReadyError`][wybthon.NotReadyError], reads during a recompute
  return the previous value, and every resume after an `await` tracks
  dependencies just like the code before it.
- **One flush, three phases.** Render effects (holes and prop
  bindings) run first, then the buffered DOM ops are committed across
  the bridge once, then user effects run and observe the committed DOM.
  Writes made during a flush loop the phases until the graph settles.

Everything public here is re-exported from `wybthon.reactivity` and
`wybthon`; application code never imports `_core` directly.
"""

from __future__ import annotations

import asyncio
import gc
import inspect
from collections.abc import Awaitable as AbcAwaitable
from collections.abc import Callable
from types import FunctionType, MethodType
from typing import Any, Final

from .. import _warnings
from .._warnings import log_error, warn_once

__all__ = [
    "Accessor",
    "Signal",
    "Computation",
    "Memo",
    "Prop",
    "Owner",
    "NotReadyError",
    "WriteInScopeError",
    "flush",
    "untrack",
    "get_owner",
    "run_with_owner",
    "get_observer",
    "is_accessor",
]

# ---------------------------------------------------------------------------
# Sentinels and constants
# ---------------------------------------------------------------------------

_DEFAULT_EQUALS: Final = object()
_MISSING: Final = object()

# Node states (graph coloring for the push-mark / pull-recompute scheduler).
_CLEAN: Final = 0
_CHECK: Final = 1
_DIRTY: Final = 2

# Computation kinds.
_K_MEMO: Final = 0
_K_RENDER: Final = 1
_K_EFFECT: Final = 2

# Safety valve: the maximum number of settle rounds in one flush before we
# assume a runaway cycle (an effect writing its own dependency forever).
_MAX_FLUSH_ROUNDS: Final = 10_000

# Sentinel key under which ``Loading`` stores its collector on an owner's
# context map. Lives here so async reads can find the nearest boundary
# without importing UI modules.
LOADING_CONTEXT_KEY: Final = "__wyb_loading__"


# ---------------------------------------------------------------------------
# Global reactive state
# ---------------------------------------------------------------------------

_current_owner: Owner | None = None
_current_observer: Computation | None = None

# Depth of nested ``untrack`` calls. Reads inside are not tracked and the
# dev-mode top-level-read warning stays quiet.
_untrack_depth: int = 0

# Depth of component bodies currently executing (set by the reconciler).
# While positive, an untracked reactive read outside ``untrack`` is the
# "top-level reactive read" footgun and warns in dev mode.
_setup_depth: int = 0
_setup_component: Any = None

# Signals with a staged (uncommitted) write, in write order.
_staged: list[Signal[Any]] = []

# Effects dirtied since the last drain, by phase.
_render_queue: list[Computation] = []
_effect_queue: list[Computation] = []

# Callbacks registered with ``on_settled`` that run once the flush that
# mounted them has fully settled and committed.
_settled_queue: list[Callable[[], Any]] = []

# Sources that lost their last observer; checked after the flush so a
# recompute that drops and re-adds an edge doesn't fire ``unobserved``.
_unobserved_check: list[Any] = []

_flushing: bool = False
_flush_scheduled: bool = False

# Stack of in-progress ``is_pending`` probes; while non-empty, async reads
# record their pending state on the top entry instead of only returning.
_pending_probe: list[bool] = []

# Depth of nested ``latest`` calls; while positive, not-ready reads return
# their placeholder instead of raising ``NotReadyError``.
_latest_depth: int = 0

# Cached microtask scheduler: ``None`` = not probed, ``False`` = none
# available, otherwise ``(queueMicrotask, create_once_callable)``.
_js_microtask: Any = None

# The DOM command buffer's commit function (a no-op when the buffer is
# empty, e.g. pure CPython usage). Bound lazily so the reactive core has
# no import-time dependency on the kernel.
_kernel_commit: Callable[[], None] | None = None


def _commit_dom() -> None:
    global _kernel_commit
    fn = _kernel_commit
    if fn is None:
        from ..kernel import commit

        fn = _kernel_commit = commit
    fn()


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class NotReadyError(Exception):
    """Raised when reading an async computation that has no value yet.

    Propagates "not ready" through the graph: a memo whose body reads a
    pending async memo becomes pending itself, and a reactive hole that
    hits `NotReadyError` keeps its previous content while the nearest
    [`Loading`][wybthon.Loading] boundary shows its fallback.

    Application code rarely raises or catches this directly; use
    [`is_pending`][wybthon.is_pending] and [`latest`][wybthon.latest]
    to observe pending state without suspending.
    """


class WriteInScopeError(RuntimeError):
    """Raised (in dev mode) when a signal is written inside a tracking scope.

    Writing a signal from a memo body, a single-function effect, or a
    reactive hole is almost always a bug: derive the value with
    [`create_memo`][wybthon.create_memo] instead, or move the write
    into the untracked `apply` stage of a split
    [`create_effect`][wybthon.create_effect], an event handler, or an
    [`action`][wybthon.action].
    """


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _changed(equals: Any, old: Any, new: Any) -> bool:
    """Return True when `new` counts as a change from `old` under `equals`.

    - `equals=False`: always changed.
    - callable: changed when `equals(old, new)` is falsy.
    - default: identity fast path, then `==`.
    """
    if equals is False:
        return True
    if callable(equals):
        try:
            return not bool(equals(old, new))
        except Exception:
            return True
    if new is old:
        return False
    try:
        return not bool(new == old)
    except Exception:
        return True


def _warn_top_level_read(source: Any) -> None:
    component = _setup_component
    from .._warnings import component_name

    label = source._label() if hasattr(source, "_label") else repr(source)
    warn_once(
        "top_level_read",
        (id(component), label),
        f"Component {component_name(component)} read reactive value {label} at the top level of its body. "
        "That read isn't tracked, so later updates won't reach it. Read it inside the returned tree, a "
        "create_memo/create_effect, or make the one-time read explicit with .peek() or untrack().",
    )


def _accepts_positional(fn: Any) -> bool:
    """Return True when `fn` declares at least one required positional parameter."""
    code = getattr(fn, "__code__", None)
    if code is not None:
        defaults = getattr(fn, "__defaults__", None)
        n = code.co_argcount - (len(defaults) if defaults else 0)
        if getattr(fn, "__self__", None) is not None:
            n -= 1
        return n > 0
    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return False
    return any(
        p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
        and p.default is inspect.Parameter.empty
        for p in sig.parameters.values()
    )


def _positional_count(fn: Any) -> int:
    """Return how many positional parameters `fn` accepts (``-1`` for unbounded)."""
    code = getattr(fn, "__code__", None)
    if code is not None:
        if code.co_flags & inspect.CO_VARARGS:
            return -1
        n = code.co_argcount
        if getattr(fn, "__self__", None) is not None:
            n -= 1
        return n
    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return -1
    n = 0
    for p in sig.parameters.values():
        if p.kind is inspect.Parameter.VAR_POSITIONAL:
            return -1
        if p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD):
            n += 1
    return n


# ---------------------------------------------------------------------------
# Scheduling
# ---------------------------------------------------------------------------


def _schedule_microtask(fn: Callable[[], None]) -> bool:
    """Schedule `fn` on the soonest async tick; False when none is available."""
    global _js_microtask
    if _js_microtask is None:
        try:
            import js as _js
            from pyodide.ffi import create_once_callable as _once

            _js_microtask = (_js.queueMicrotask, _once)
        except Exception:
            _js_microtask = False
    if _js_microtask:
        try:
            qm, once = _js_microtask
            qm(once(fn))
            return True
        except Exception:
            pass
    try:
        asyncio.get_running_loop().call_soon(fn)
        return True
    except Exception:
        return False


def _schedule_flush() -> None:
    """Request a flush on the next tick (no-op while one is scheduled or running)."""
    global _flush_scheduled
    if _flush_scheduled or _flushing:
        return
    if _schedule_microtask(_run_scheduled_flush):
        _flush_scheduled = True


def _run_scheduled_flush() -> None:
    global _flush_scheduled
    _flush_scheduled = False
    _flush()


def flush() -> None:
    """Apply staged writes, run every dirty effect, and commit the DOM now.

    Writes become visible to reads only when the graph flushes. In the
    browser that happens automatically on a microtask and after every
    event handler; call `flush()` when you need the settled state
    *now*, for example right after a write in synchronous test code.

    Safe to call at any time; a no-op when nothing is pending, and a
    no-op inside an effect (the running flush finishes the work).

    Example:
        ```python
        count, set_count = create_signal(0)
        set_count(1)
        count()   # 0: the write is staged
        flush()
        count()   # 1
        ```
    """
    global _flush_scheduled
    _flush_scheduled = False
    _flush()


def _commit_staged() -> None:
    """Make staged writes visible and mark their observers dirty."""
    while _staged:
        batch = list(_staged)
        _staged.clear()
        for sig in batch:
            sig._commit()


def _drain(queue: list[Computation]) -> None:
    i = 0
    try:
        while i < len(queue):
            comp = queue[i]
            i += 1
            if not comp._disposed:
                comp._update_if_necessary()
    finally:
        queue.clear()


# Depth of nested commit windows (flushes and initial mounts) that have
# paused the cyclic garbage collector, and whether it was enabled before.
_gc_pause_depth: int = 0
_gc_was_enabled: bool = False


def _gc_pause() -> None:
    """Pause the cyclic GC for the duration of a commit window.

    A flush (or an initial mount) allocates in bursts: VNodes,
    computations, prop maps, and DOM ops that almost all outlive the
    window. CPython's generational collector counts those allocations and
    runs collections in the middle of the work, each of which traverses a
    heap that grows with the app; on a 10k-row mount that roughly doubles
    the wall time without freeing anything. Pausing the collector until
    the window closes lets the garbage that a window does produce be
    collected in one pass afterwards. Reference counting is unaffected.
    """
    global _gc_pause_depth, _gc_was_enabled
    if _gc_pause_depth == 0:
        _gc_was_enabled = gc.isenabled()
        if _gc_was_enabled:
            gc.disable()
    _gc_pause_depth += 1


def _gc_resume() -> None:
    global _gc_pause_depth
    _gc_pause_depth -= 1
    if _gc_pause_depth == 0 and _gc_was_enabled:
        gc.enable()


def _flush() -> None:
    """Settle the graph: commit writes, run effects by phase, commit DOM, repeat."""
    global _flushing
    if _flushing:
        return
    _flushing = True
    rounds = 0
    _gc_pause()
    try:
        while True:
            while True:
                rounds += 1
                if rounds > _MAX_FLUSH_ROUNDS:
                    raise RuntimeError(
                        "Wybthon: reactive update did not stabilize "
                        "(an effect is probably writing its own dependency)."
                    )
                if _staged:
                    _commit_staged()
                if _render_queue:
                    _drain(_render_queue)
                    continue
                _commit_dom()
                if _staged:
                    continue
                if _effect_queue:
                    _drain(_effect_queue)
                    continue
                break
            if _settled_queue:
                callbacks = list(_settled_queue)
                _settled_queue.clear()
                for cb in callbacks:
                    try:
                        cb()
                    except Exception as exc:
                        log_error(f"on_settled callback raised: {exc}", exc)
                if _staged or _render_queue or _effect_queue or _settled_queue:
                    continue
            break
        if _unobserved_check:
            pending = list(_unobserved_check)
            _unobserved_check.clear()
            for src in pending:
                src._check_unobserved()
    finally:
        _staged.clear()
        _render_queue.clear()
        _effect_queue.clear()
        _flushing = False
        _gc_resume()


def _reset_scheduler_for_tests() -> None:
    """Test-only: drop staged writes, effect queues, and scheduler flags."""
    global _flush_scheduled, _flushing, _kernel_commit, _setup_depth, _setup_component
    _staged.clear()
    _render_queue.clear()
    _effect_queue.clear()
    _settled_queue.clear()
    _unobserved_check.clear()
    _pending_probe.clear()
    _flush_scheduled = False
    _flushing = False
    _kernel_commit = None
    _setup_depth = 0
    _setup_component = None
    from . import _actions

    _actions._inflight = 0
    _actions._reverts.clear()


# ---------------------------------------------------------------------------
# Owner: the ownership tree
# ---------------------------------------------------------------------------


class Owner:
    """A reactive ownership scope.

    Owners form a tree. Disposing an owner disposes its children first
    (depth-first), then runs its own cleanup callbacks LIFO. Every
    computation is an owner, as is each component instance, each
    `For` row, and each `create_root`.

    Owners also carry context values (see
    [`create_context`][wybthon.create_context]) and an optional error
    handler installed by [`Errored`][wybthon.Errored].
    """

    __slots__ = ("_parent", "_children", "_cleanups", "_disposed", "_context_map", "_error_handler")

    def __init__(self) -> None:
        self._parent: Owner | None = None
        # Keyed by ``id(child)`` so an individually disposed child detaches
        # in O(1); a row leaving a 10k-row list would otherwise pay a
        # linear ``list.remove`` against its parent.
        self._children: dict[int, Owner] | None = None
        self._cleanups: list[Callable[[], Any]] | None = None
        self._disposed: bool = False
        self._context_map: dict[Any, Any] | None = None
        self._error_handler: Callable[[BaseException, Computation | None], Any] | None = None

    def _add_child(self, child: Owner) -> None:
        child._parent = self
        if self._children is None:
            self._children = {id(child): child}
        else:
            self._children[id(child)] = child

    def _add_cleanup(self, fn: Callable[[], Any]) -> None:
        if self._cleanups is None:
            self._cleanups = [fn]
        else:
            self._cleanups.append(fn)

    def _dispose_children(self) -> None:
        children = self._children
        if not children:
            return
        items = list(children.values())
        children.clear()
        for child in items:
            child._parent = None
            child.dispose()

    def _run_cleanups(self) -> None:
        cleanups = self._cleanups
        if not cleanups:
            return
        # Cleanups run untracked: a subtree is often torn down from inside a
        # re-rendering hole, and a cleanup that writes a signal (a "mounted"
        # counter, a subscription flag) must neither subscribe that hole
        # nor trip the dev-mode write guard.
        global _current_observer
        prev_obs = _current_observer
        _current_observer = None
        try:
            while cleanups:
                fn = cleanups.pop()
                try:
                    fn()
                except Exception as exc:
                    log_error(f"Cleanup callback raised: {exc}", exc)
        finally:
            _current_observer = prev_obs

    def _set_context(self, key: Any, value: Any) -> None:
        if self._context_map is None:
            self._context_map = {}
        self._context_map[key] = value

    def _lookup_context(self, key: Any, default: Any) -> Any:
        owner: Owner | None = self
        while owner is not None:
            cm = owner._context_map
            if cm is not None and key in cm:
                return cm[key]
            owner = owner._parent
        return default

    def dispose(self) -> None:
        """Tear down this owner and every descendant.

        Children are disposed depth-first, then this owner's cleanups
        run in LIFO order, then it detaches from its parent. Later calls
        are no-ops.
        """
        if self._disposed:
            return
        self._disposed = True
        self._dispose_children()
        self._run_cleanups()
        parent = self._parent
        if parent is not None:
            if parent._children is not None:
                parent._children.pop(id(self), None)
            self._parent = None


class _ComponentContext(Owner):
    """Ownership scope for one mounted component instance."""

    __slots__ = ("_props", "_vnode", "_component")

    def __init__(self, component: Any) -> None:
        super().__init__()
        self._props: Any = None
        self._vnode: Any = None
        self._component = component


def _nearest_component() -> _ComponentContext | None:
    owner = _current_owner
    while owner is not None:
        if isinstance(owner, _ComponentContext):
            return owner
        owner = owner._parent
    return None


# ---------------------------------------------------------------------------
# Accessor: the read protocol
# ---------------------------------------------------------------------------


class Accessor[T]:
    """A zero-argument callable that returns a reactive value.

    Calling an accessor inside a tracking scope (a memo, an effect's
    compute stage, or a reactive hole) subscribes that scope to the
    value. [`peek`][wybthon.Accessor.peek] reads without subscribing.

    Every reactive read in Wybthon goes through an `Accessor`:
    [`create_signal`][wybthon.create_signal] getters are
    [`Signal`][wybthon.Signal]s, [`create_memo`][wybthon.create_memo]
    returns a [`Memo`][wybthon.Memo], and component parameters are
    [`Prop`][wybthon.Prop]s. Embedding an accessor in a VNode tree
    creates a reactive hole. Type it as `Accessor[T]` in signatures
    when you accept any of them.
    """

    __slots__ = ()

    def __call__(self) -> T:
        """Return the current value and subscribe the active tracking scope."""
        raise NotImplementedError

    def peek(self) -> T:
        """Return the current value without subscribing anything."""
        raise NotImplementedError

    def _label(self) -> str:
        return type(self).__name__


# ---------------------------------------------------------------------------
# Signal
# ---------------------------------------------------------------------------


class Signal[T](Accessor[T]):
    """Mutable reactive container; the accessor half of `create_signal`.

    Reading a `Signal` (calling it) returns the **committed** value and
    subscribes the active tracking scope. [`set`][wybthon.Signal.set]
    stages a write that becomes visible at the next flush.

    Most code destructures `create_signal` into `(getter, setter)`;
    `Signal` is public so it can appear in type hints and so
    self-contained reactive fields (as in
    [`Field`][wybthon.Field]) can carry their own setter.

    Args:
        value: The initial value.
        equals: Equality policy; see [`create_signal`][wybthon.create_signal].
        unobserved: Optional callback invoked when the signal loses its
            last subscriber (resource cleanup).
        name: Optional label used in dev-mode diagnostics.
    """

    __slots__ = ("_value", "_pending", "_staged", "_observers", "_equals", "_unobserved", "_name")

    def __init__(
        self,
        value: T,
        *,
        equals: Any = _DEFAULT_EQUALS,
        unobserved: Callable[[], Any] | None = None,
        name: str | None = None,
    ) -> None:
        self._value: T = value
        self._pending: Any = None
        self._staged: bool = False
        self._observers: dict[Computation, None] | None = None
        self._equals = equals
        self._unobserved = unobserved
        self._name = name

    def _label(self) -> str:
        return f"signal {self._name!r}" if self._name else "a signal"

    # -- source protocol ----------------------------------------------------

    def _add_observer(self, comp: Computation) -> None:
        obs = self._observers
        if obs is None:
            self._observers = {comp: None}
        else:
            obs[comp] = None

    def _remove_observer(self, comp: Computation) -> None:
        obs = self._observers
        if obs is not None:
            obs.pop(comp, None)
            if not obs and self._unobserved is not None:
                _unobserved_check.append(self)
                _schedule_flush()

    def _check_unobserved(self) -> None:
        if not self._observers and self._unobserved is not None:
            try:
                self._unobserved()
            except Exception as exc:
                log_error(f"unobserved callback raised: {exc}", exc)

    def _update_if_necessary(self) -> None:
        """Source-interface no-op; a signal's committed value is always current."""

    # -- reads ----------------------------------------------------------------

    def __call__(self) -> T:
        obs = _current_observer
        if obs is not None:
            obs._add_source(self)
        elif _setup_depth and not _untrack_depth:
            _warn_top_level_read(self)
        return self._value

    def peek(self) -> T:
        """Return the committed value without subscribing."""
        return self._value

    def _latest(self) -> Any:
        """The staged value if a write is pending, else the committed value."""
        return self._pending if self._staged else self._value

    # -- writes ---------------------------------------------------------------

    def set(self, value: T | Callable[[T], T]) -> T:
        """Stage a write; the new value is visible after the next flush.

        Supports **functional updates**: when `value` is callable it
        receives the latest value (including any write staged earlier
        in the same batch) and its result is stored, so two
        `set(lambda n: n + 1)` calls in one handler add two. To store a
        callable *as* the value, wrap it: `set(lambda _: my_fn)`.

        In dev mode, writing from inside a tracking scope raises
        [`WriteInScopeError`][wybthon.WriteInScopeError].

        Args:
            value: The new value, or an updater `(current) -> new`.

        Returns:
            The value that was staged.
        """
        if _current_observer is not None and _warnings.DEV_MODE:
            raise WriteInScopeError(
                f"Cannot write {self._label()} inside a tracking scope (memo, effect compute stage, or "
                "reactive hole). Derive the value with create_memo, or write it from the apply stage "
                "of a split create_effect, an event handler, or an action."
            )
        if callable(value):
            value = value(self._latest())
        self._set(value)
        return value

    def _set(self, value: Any) -> None:
        """Stage `value` without the dev-mode scope check (framework internal)."""
        if self._staged:
            self._pending = value
            return
        if not _changed(self._equals, self._value, value):
            return
        self._pending = value
        self._staged = True
        _staged.append(self)
        _schedule_flush()

    def _commit(self) -> None:
        if not self._staged:
            return
        self._staged = False
        new = self._pending
        self._pending = None
        if not _changed(self._equals, self._value, new):
            return
        self._value = new
        obs = self._observers
        if obs:
            for o in list(obs):
                o._stale(_DIRTY)

    def _set_now(self, value: Any) -> None:
        """Commit `value` immediately (framework internal, for derived per-row state).

        Used where the signal's value is a function of data the graph is
        already recomputing (a list row's index), so staging would only
        delay consistency by a round.
        """
        if self._staged:
            self._staged = False
            self._pending = None
            try:
                _staged.remove(self)
            except ValueError:
                pass
        if not _changed(self._equals, self._value, value):
            return
        self._value = value
        obs = self._observers
        if obs:
            for o in list(obs):
                o._stale(_DIRTY)

    def __repr__(self) -> str:
        return f"Signal({self._value!r})"


# ---------------------------------------------------------------------------
# Accessor detection
# ---------------------------------------------------------------------------


def is_accessor(value: Any) -> bool:
    """Return True when `value` is a reactive expression: an `Accessor` or a zero-arg function.

    This is the single rule the framework uses to decide what becomes a
    reactive hole (as a child), a reactive binding (as a prop), or an
    auto-unwrapped component prop. Plain functions and lambdas qualify
    when they take no required positional arguments; bound methods
    likewise. Classes, `Ref`s, components, and callbacks that take
    arguments do not.
    """
    if isinstance(value, Accessor):
        return True
    t = type(value)
    if t is FunctionType:
        code = value.__code__
        defaults = value.__defaults__
        return code.co_argcount - (len(defaults) if defaults else 0) <= 0
    if t is MethodType:
        fn = value.__func__
        code = getattr(fn, "__code__", None)
        if code is None:
            return False
        defaults = fn.__defaults__
        return code.co_argcount - 1 - (len(defaults) if defaults else 0) <= 0
    return False


def _unwrap(value: Any) -> Any:
    """Call `value` if it's a reactive expression (tracked), else return it."""
    if isinstance(value, Accessor):
        return value()
    if type(value) is FunctionType:
        code = value.__code__
        defaults = value.__defaults__
        if code.co_argcount - (len(defaults) if defaults else 0) <= 0:
            return value()
    return value


# ---------------------------------------------------------------------------
# Prop: a component parameter
# ---------------------------------------------------------------------------


class Prop[T](Accessor[T]):
    """Reactive accessor for one component prop.

    Every parameter of a [`@component`][wybthon.component] function is
    bound to a `Prop`. Calling it returns the current value the parent
    passed (tracked); if the parent passed an accessor or a zero-arg
    function, it's unwrapped transparently, so children always read
    `name()` regardless of whether the parent wrote `name="Ada"` or
    `name=lambda: user().name`.

    Embed the `Prop` itself in the returned tree (`p("Hello, ", name)`)
    to create a reactive hole that updates when the parent's value
    changes; call it inside memos, effects, and holes to derive from
    it. Reading it at the top level of the component body freezes the
    value and warns in dev mode; use `.peek()` when that's intended.
    """

    __slots__ = ("_sig", "_key")

    def __init__(self, sig: Signal[Any], key: str) -> None:
        self._sig = sig
        self._key = key

    def _label(self) -> str:
        return f"prop {self._key!r}"

    def __call__(self) -> T:
        sig = self._sig
        obs = _current_observer
        if obs is not None:
            obs._add_source(sig)
        elif _setup_depth and not _untrack_depth:
            _warn_top_level_read(self)
        value = sig._value
        if isinstance(value, Accessor):
            return value()
        if type(value) is FunctionType:
            code = value.__code__
            defaults = value.__defaults__
            if code.co_argcount - (len(defaults) if defaults else 0) <= 0:
                return value()
        return value

    def peek(self) -> T:
        """Return the current (unwrapped) value without subscribing."""
        value = self._sig._value
        if isinstance(value, Accessor):
            return value.peek()
        if type(value) is FunctionType:
            code = value.__code__
            defaults = value.__defaults__
            if code.co_argcount - (len(defaults) if defaults else 0) <= 0:
                return untrack(value)
        return value

    def __repr__(self) -> str:
        return f"Prop({self._key!r})"


# ---------------------------------------------------------------------------
# Async bookkeeping
# ---------------------------------------------------------------------------


class _AsyncState:
    """Per-computation async state, allocated on first use."""

    __slots__ = ("pending", "has_value", "version", "pending_signal", "quiet", "inflight", "inflight_signal", "closer")

    def __init__(self) -> None:
        self.pending: bool = False
        self.has_value: bool = False
        self.version: int = 0
        self.pending_signal: Signal[bool] | None = None
        # A quiet run (``refresh``) recomputes without reporting pending.
        self.quiet: bool = False
        # True while a launched run is outstanding, quiet or not, so
        # ``resolve``/``refresh`` awaiters can wait for it to settle.
        self.inflight: bool = False
        self.inflight_signal: Signal[bool] | None = None
        # Cleanup for an in-flight async generator.
        self.closer: Callable[[], Any] | None = None


# ---------------------------------------------------------------------------
# Computation
# ---------------------------------------------------------------------------


class Computation(Owner):
    """A tracked function: the node type behind memos and effects.

    A computation re-runs when a source it read changes. It's also an
    owner: children created during a run are disposed before the next
    run, so conditionally created effects never leak.

    Kinds:

    - **memo**: carries a value that other computations can read.
    - **render effect**: runs in the render phase of a flush (holes and
      prop bindings) before the DOM commit.
    - **effect**: runs after the DOM commit and may have a split
      compute/apply shape.
    """

    __slots__ = (
        "_fn",
        "_pass_prev",
        "_sources",
        "_state",
        "_kind",
        "_value",
        "_observers",
        "_equals",
        "_error",
        "_async",
        "_apply",
        "_apply_arity",
        "_defer",
        "_first",
        "_apply_cleanup",
        "_error_fn",
        "_lazy",
        "_unobserved",
        "_name",
    )

    def __init__(
        self,
        fn: Callable[..., Any],
        *,
        kind: int,
        value: Any = None,
        equals: Any = _DEFAULT_EQUALS,
        apply: Callable[..., Any] | None = None,
        defer: bool = False,
        error: Callable[[BaseException], Any] | None = None,
        lazy: bool = False,
        unobserved: Callable[[], Any] | None = None,
        pass_prev: bool | None = None,
        name: str | None = None,
    ) -> None:
        super().__init__()
        self._fn = fn
        self._pass_prev = _accepts_positional(fn) if pass_prev is None else pass_prev
        self._sources: dict[Any, None] | None = None
        self._state: int = _DIRTY
        self._kind = kind
        self._value: Any = value
        self._observers: dict[Computation, None] | None = None
        self._equals = equals
        self._error: BaseException | None = None
        self._async: _AsyncState | None = None
        self._apply = apply
        self._apply_arity = _positional_count(apply) if apply is not None else 0
        self._defer = defer
        self._first = True
        self._apply_cleanup: Callable[[], Any] | None = None
        self._error_fn = error
        self._lazy = lazy
        self._unobserved = unobserved
        self._name = name

    def _label(self) -> str:
        if self._name:
            return f"memo {self._name!r}"
        return f"memo {getattr(self._fn, '__name__', '<fn>')!r}"

    # -- source side (memos are sources for other computations) ---------------

    def _add_observer(self, comp: Computation) -> None:
        obs = self._observers
        if obs is None:
            self._observers = {comp: None}
        else:
            obs[comp] = None

    def _remove_observer(self, comp: Computation) -> None:
        obs = self._observers
        if obs is not None:
            obs.pop(comp, None)
            if not obs and (self._unobserved is not None or self._lazy):
                _unobserved_check.append(self)
                _schedule_flush()

    def _check_unobserved(self) -> None:
        if self._disposed or self._observers:
            return
        if self._unobserved is not None:
            try:
                self._unobserved()
            except Exception as exc:
                log_error(f"unobserved callback raised: {exc}", exc)
        if self._lazy:
            self.dispose()

    # -- observer side ---------------------------------------------------------

    def _add_source(self, source: Any) -> None:
        srcs = self._sources
        if srcs is None:
            self._sources = {source: None}
            source._add_observer(self)
        elif source not in srcs:
            srcs[source] = None
            source._add_observer(self)

    def _clear_sources(self) -> None:
        srcs = self._sources
        if srcs:
            for src in srcs:
                src._remove_observer(self)
            srcs.clear()

    # -- scheduling -------------------------------------------------------------

    def _stale(self, state: int) -> None:
        """Mark this node CHECK or DIRTY and propagate CHECK to observers."""
        if self._disposed:
            return
        if self._state < state:
            was_clean = self._state == _CLEAN
            self._state = state
            if was_clean:
                kind = self._kind
                if kind == _K_RENDER:
                    _render_queue.append(self)
                    _schedule_flush()
                elif kind == _K_EFFECT:
                    _effect_queue.append(self)
                    _schedule_flush()
                obs = self._observers
                if obs:
                    for o in list(obs):
                        o._stale(_CHECK)

    def _update_if_necessary(self) -> None:
        """Bring this node up to date by pulling its sources (glitch-free)."""
        if self._disposed or self._state == _CLEAN:
            return
        if self._state == _CHECK:
            srcs = self._sources
            if srcs:
                for src in list(srcs):
                    src._update_if_necessary()
                    if self._state == _DIRTY:
                        break
        if self._state == _DIRTY:
            # CLEAN first so a write to one of our own sources made during
            # the run re-dirties us instead of being swallowed.
            self._state = _CLEAN
            self._update()
        else:
            self._state = _CLEAN

    # -- errors -----------------------------------------------------------------

    def _handle_error(self, exc: BaseException) -> bool:
        """Route `exc` to `error=` or the nearest owner error handler."""
        if self._error_fn is not None:
            try:
                self._error_fn(exc)
            except Exception as inner:
                log_error(f"Effect error handler raised: {inner}", inner)
            return True
        owner: Owner | None = self._parent
        while owner is not None:
            handler = owner._error_handler
            if handler is not None:
                try:
                    handler(exc, self)
                except Exception as inner:
                    log_error(f"Error handler raised: {inner}", inner)
                return True
            owner = owner._parent
        return False

    # -- execution ------------------------------------------------------------

    def _update(self) -> None:
        """Re-run the tracked function and refresh the dependency set."""
        if self._disposed:
            return
        self._dispose_children()
        self._run_cleanups()
        self._clear_sources()
        a = self._async
        if a is not None:
            a.version += 1
            closer = a.closer
            if closer is not None:
                a.closer = None
                try:
                    closer()
                except Exception:
                    pass
        global _current_owner, _current_observer
        prev_owner = _current_owner
        prev_obs = _current_observer
        _current_owner = self
        _current_observer = self
        try:
            new_value = self._fn(self._value) if self._pass_prev else self._fn()
        except NotReadyError:
            self._mark_pending()
            return
        except Exception as exc:
            self._fail(exc)
            return
        finally:
            _current_owner = prev_owner
            _current_observer = prev_obs
        if isinstance(new_value, AbcAwaitable):
            self._launch(new_value)
            return
        if inspect.isasyncgen(new_value):
            self._launch_gen(new_value)
            return
        if a is not None:
            a.version += 1
            a.has_value = True
            a.quiet = False
            self._set_pending(False)
        self._error = None
        self._settle(new_value)

    def _settle(self, value: Any) -> None:
        """Accept a new value: notify memo observers or run an effect's apply stage."""
        if self._kind == _K_MEMO:
            if self._first or _changed(self._equals, self._value, value):
                self._first = False
                self._value = value
                obs = self._observers
                if obs:
                    for o in list(obs):
                        o._stale(_DIRTY)
            return
        prev = self._value
        self._value = value
        apply = self._apply
        if apply is None:
            self._first = False
            return
        if self._first and self._defer:
            self._first = False
            return
        self._first = False
        cleanup = self._apply_cleanup
        if cleanup is not None:
            self._apply_cleanup = None
            try:
                cleanup()
            except Exception as exc:
                log_error(f"Effect cleanup raised: {exc}", exc)
        global _current_observer
        prev_obs = _current_observer
        _current_observer = None
        try:
            result = apply(value) if self._apply_arity == 1 else apply(value, prev)
        except Exception as exc:
            if not self._handle_error(exc):
                raise
            return
        finally:
            _current_observer = prev_obs
        if callable(result):
            self._apply_cleanup = result
            self._add_cleanup(self._run_apply_cleanup)

    def _run_apply_cleanup(self) -> None:
        cleanup = self._apply_cleanup
        if cleanup is not None:
            self._apply_cleanup = None
            cleanup()

    def _fail(self, exc: BaseException) -> None:
        """Record or route an exception raised by the body."""
        if self._kind == _K_MEMO:
            self._error = exc
            if self._async is not None:
                self._set_pending(False)
            obs = self._observers
            if obs:
                for o in list(obs):
                    o._stale(_DIRTY)
            return
        if self._async is not None:
            self._set_pending(False)
        if not self._handle_error(exc):
            raise exc

    # -- async ------------------------------------------------------------------

    def _ensure_async(self) -> _AsyncState:
        a = self._async
        if a is None:
            a = _AsyncState()
            self._async = a
        return a

    def _pending_sig(self) -> Signal[bool]:
        a = self._ensure_async()
        if a.pending_signal is None:
            a.pending_signal = Signal(a.pending)
        return a.pending_signal

    def _set_pending(self, value: bool) -> None:
        a = self._ensure_async()
        if a.pending == value:
            return
        a.pending = value
        if a.pending_signal is not None:
            a.pending_signal._set(value)

    def _inflight_sig(self) -> Signal[bool]:
        a = self._ensure_async()
        if a.inflight_signal is None:
            a.inflight_signal = Signal(a.inflight)
        return a.inflight_signal

    def _set_inflight(self, value: bool) -> None:
        a = self._ensure_async()
        if a.inflight == value:
            return
        a.inflight = value
        if a.inflight_signal is not None:
            # Committed immediately: an awaiter probes it synchronously right
            # after the run launches, and the launch/settle paths schedule
            # the flush that re-runs observers.
            a.inflight_signal._set_now(value)

    def _mark_pending(self) -> None:
        """A source isn't ready; stay pending until its resolution re-runs us."""
        a = self._ensure_async()
        self._error = None
        quiet, a.quiet = a.quiet, False
        if not quiet:
            self._set_pending(True)

    def _launch(self, awaitable: Any) -> None:
        """Drive `awaitable` with tracking active on every resume."""
        a = self._ensure_async()
        a.version += 1
        version = a.version
        self._error = None
        quiet, a.quiet = a.quiet, False
        if not quiet:
            self._set_pending(True)
        self._set_inflight(True)
        _schedule_flush()

        if asyncio.iscoroutine(awaitable):
            coro = awaitable
        else:

            async def _wrap() -> Any:
                return await awaitable

            coro = _wrap()

        def on_done(value: Any) -> None:
            self._resolve(version, value)

        def on_error(exc: BaseException) -> None:
            self._reject(version, exc)

        self._step(coro, version, on_done, on_error)

    def _launch_gen(self, agen: Any) -> None:
        """Drive an async generator: each yielded value becomes the new value."""
        a = self._ensure_async()
        a.version += 1
        version = a.version
        self._error = None
        quiet, a.quiet = a.quiet, False
        if not quiet:
            self._set_pending(True)
        self._set_inflight(True)
        _schedule_flush()

        def closer() -> None:
            try:
                res = agen.aclose()
                if inspect.iscoroutine(res):
                    res.close()
            except Exception:
                pass

        a.closer = closer

        def advance() -> None:
            if self._disposed or self._async is None or self._async.version != version:
                return
            self._step(agen.__anext__(), version, on_value, on_error)

        def on_value(value: Any) -> None:
            self._resolve(version, value, final=False)
            advance()

        def on_error(exc: BaseException) -> None:
            if isinstance(exc, StopAsyncIteration):
                a2 = self._async
                if a2 is not None and a2.version == version:
                    a2.closer = None
                    if not a2.has_value:
                        self._resolve(version, None)
                    else:
                        self._set_pending(False)
                        self._set_inflight(False)
                        _schedule_flush()
                return
            self._reject(version, exc)

        advance()

    def _step(
        self,
        coro: Any,
        version: int,
        on_done: Callable[[Any], None],
        on_error: Callable[[BaseException], None],
    ) -> None:
        """Drive a coroutine so every resume runs as this observer."""

        def alive() -> bool:
            return not self._disposed and self._async is not None and self._async.version == version

        # A ``NotReadyError`` after an await means a pending source was read;
        # its subscription is in place, so its resolution re-runs us from the
        # top. Nothing to do here.
        _drive_coroutine(coro, owner=self, observer=self, alive=alive, on_done=on_done, on_error=on_error)

    def _resolve(self, version: int, value: Any, *, final: bool = True) -> None:
        a = self._async
        if self._disposed or a is None or a.version != version:
            return
        self._error = None
        a.has_value = True
        if final:
            a.closer = None
            self._set_inflight(False)
        self._set_pending(False)
        self._settle(value)
        _schedule_flush()

    def _reject(self, version: int, exc: BaseException) -> None:
        a = self._async
        if self._disposed or a is None or a.version != version:
            return
        a.closer = None
        self._set_inflight(False)
        if self._kind == _K_MEMO:
            self._error = exc
            self._set_pending(False)
            obs = self._observers
            if obs:
                for o in list(obs):
                    o._stale(_DIRTY)
        else:
            self._set_pending(False)
            if not self._handle_error(exc):
                log_error(f"Async effect raised: {exc}", exc if isinstance(exc, Exception) else None)
        _schedule_flush()

    def _register_with_loading(self) -> None:
        owner = _current_owner
        if owner is None:
            return
        collector = owner._lookup_context(LOADING_CONTEXT_KEY, None)
        if collector is not None:
            collector.register(self)

    def _refresh(self) -> None:
        """Recompute quietly: no pending state is reported while the run is in flight."""
        if self._disposed:
            return
        self._ensure_async().quiet = True
        self._state = _DIRTY
        self._update_if_necessary()

    # -- reads -------------------------------------------------------------------

    def _read(self) -> Any:
        """Read a memo: bring it current, subscribe the reader, surface async state."""
        self._update_if_necessary()
        obs = _current_observer
        if obs is not None:
            if obs is not self and not self._disposed:
                obs._add_source(self)
        elif _setup_depth and not _untrack_depth:
            _warn_top_level_read(self)
        a = self._async
        if a is not None:
            if _pending_probe and self._pending_sig()():
                _pending_probe[-1] = True
            if a.pending and not a.has_value and self._error is None:
                if _latest_depth == 0:
                    if not _pending_probe:
                        self._register_with_loading()
                    raise NotReadyError(f"Async computation has no value yet: {self._label()}")
                return self._value
        err = self._error
        if err is not None:
            raise err
        return self._value

    def dispose(self) -> None:
        """Dispose the computation and drop every dependency edge."""
        if self._disposed:
            return
        a = self._async
        if a is not None:
            a.version += 1
            closer = a.closer
            if closer is not None:
                a.closer = None
                try:
                    closer()
                except Exception:
                    pass
        self._clear_sources()
        obs = self._observers
        if obs:
            for o in list(obs):
                o_srcs = o._sources
                if o_srcs is not None:
                    o_srcs.pop(self, None)
            obs.clear()
        super().dispose()


def _event_loop() -> asyncio.AbstractEventLoop:
    """Return the running loop, or a current/new loop when none is running."""
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        pass
    try:
        return asyncio.get_event_loop_policy().get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop


def _call_soon(fn: Callable[[], None]) -> None:
    _event_loop().call_soon(fn)


def _drive_coroutine(
    coro: Any,
    *,
    owner: Owner | None,
    observer: Computation | None,
    alive: Callable[[], bool],
    on_done: Callable[[Any], None],
    on_error: Callable[[BaseException], None],
    on_not_ready: Callable[[], None] | None = None,
) -> None:
    """Step `coro` manually so each resume runs under `owner` / `observer`.

    The first step runs synchronously (so code before the first `await`
    executes immediately, like a generator action in Solid); later steps
    are scheduled by the awaited futures' completion callbacks.
    """

    def step(exc: BaseException | None = None) -> None:
        if not alive():
            try:
                coro.close()
            except Exception:
                pass
            return
        global _current_owner, _current_observer
        prev_owner = _current_owner
        prev_obs = _current_observer
        _current_owner = owner
        _current_observer = observer
        try:
            yielded = coro.throw(exc) if exc is not None else coro.send(None)
        except StopIteration as si:
            on_done(si.value)
            return
        except NotReadyError as nre:
            if on_not_ready is not None:
                on_not_ready()
            elif observer is None:
                on_error(nre)
            return
        except BaseException as e:  # noqa: BLE001 - mirrors asyncio.Task.__step
            on_error(e)
            return
        finally:
            _current_owner = prev_owner
            _current_observer = prev_obs

        blocking = getattr(yielded, "_asyncio_future_blocking", None)
        if blocking is not None:
            yielded._asyncio_future_blocking = False

            def _wakeup(fut: Any) -> None:
                try:
                    fut.result()
                except BaseException as e:  # noqa: BLE001
                    step(e)
                else:
                    step()

            yielded.add_done_callback(_wakeup)
        elif yielded is None:
            _call_soon(step)
        else:
            on_error(RuntimeError(f"Awaited an unsupported object in a reactive coroutine: {yielded!r}"))

    step()


# ---------------------------------------------------------------------------
# Memo
# ---------------------------------------------------------------------------


class Memo[T](Computation, Accessor[T]):
    """Read-only derived value; what [`create_memo`][wybthon.create_memo] returns.

    A `Memo` is both a [`Computation`][wybthon.reactivity.Computation]
    (it tracks sources and recomputes lazily) and an
    [`Accessor`][wybthon.Accessor] (call it to read). Recomputation
    happens on read after a source changed, and observers are notified
    only when the recomputed value differs under the memo's `equals`
    policy.

    Async bodies (`async def`, or an async generator) make the memo an
    async computation; see [`create_memo`][wybthon.create_memo].
    """

    __slots__ = ()

    def __init__(
        self,
        fn: Callable[..., T],
        *,
        equals: Any = _DEFAULT_EQUALS,
        lazy: bool = False,
        unobserved: Callable[[], Any] | None = None,
        name: str | None = None,
    ) -> None:
        super().__init__(fn, kind=_K_MEMO, equals=equals, lazy=lazy, unobserved=unobserved, name=name)
        if _current_owner is not None:
            _current_owner._add_child(self)

    def __call__(self) -> T:
        return self._read()

    def peek(self) -> T:
        """Return the (up-to-date) value without subscribing; `None` while not ready."""
        global _current_observer
        prev = _current_observer
        _current_observer = None
        try:
            self._update_if_necessary()
        finally:
            _current_observer = prev
        return self._value

    def __repr__(self) -> str:
        return f"Memo({self._label()})"


# ---------------------------------------------------------------------------
# Scope helpers
# ---------------------------------------------------------------------------


def untrack[T](fn: Callable[[], T]) -> T:
    """Run `fn` without tracking any reactive reads.

    Use it to read a signal inside an effect without depending on it,
    or to seed local state from a prop during component setup without
    subscribing (the dev-mode top-level-read warning is silenced inside
    `untrack`; [`Accessor.peek`][wybthon.Accessor.peek] is the shorter
    form for a single read).

    Args:
        fn: Zero-arg callable to invoke with tracking suppressed.

    Returns:
        Whatever `fn` returns.
    """
    global _current_observer, _untrack_depth
    prev = _current_observer
    _current_observer = None
    _untrack_depth += 1
    try:
        return fn()
    finally:
        _untrack_depth -= 1
        _current_observer = prev


def get_owner() -> Owner | None:
    """Return the active ownership scope, or `None` outside any scope.

    Capture it before an `await` and restore it with
    [`run_with_owner`][wybthon.run_with_owner] when you need to create
    primitives after the boundary.
    """
    return _current_owner


def get_observer() -> Computation | None:
    """Return the computation currently tracking reads, or `None`."""
    return _current_observer


def run_with_owner[T](owner: Owner | None, fn: Callable[[], T]) -> T:
    """Run `fn` under `owner` (pass `None` for no ownership) and return its result."""
    global _current_owner
    prev = _current_owner
    _current_owner = owner
    try:
        return fn()
    finally:
        _current_owner = prev


def _run_owned_untracked[T](owner: Owner | None, fn: Callable[[], T]) -> T:
    """Run `fn` owned by `owner` with tracking suppressed (list-row bodies)."""
    global _current_owner, _current_observer
    prev_owner = _current_owner
    prev_obs = _current_observer
    _current_owner = owner
    _current_observer = None
    try:
        return fn()
    finally:
        _current_owner = prev_owner
        _current_observer = prev_obs


def _enter_component_setup(ctx: _ComponentContext) -> tuple[Any, Any, Any]:
    """Install `ctx` as owner, clear tracking, and arm the top-level-read warning."""
    global _current_owner, _current_observer, _setup_depth, _setup_component
    saved = (_current_owner, _current_observer, _setup_component)
    _current_owner = ctx
    _current_observer = None
    _setup_depth += 1
    _setup_component = ctx._component
    return saved


def _exit_component_setup(saved: tuple[Any, Any, Any]) -> None:
    global _current_owner, _current_observer, _setup_depth, _setup_component
    _current_owner, _current_observer, _setup_component = saved
    _setup_depth -= 1
