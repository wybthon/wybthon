"""Signal-based reactive primitives with an ownership tree.

This module is the heart of Wybthon's SolidJS-inspired reactivity. It
implements a **synchronous, glitch-free, pull-based** reactive graph that
matches SolidJS's observable semantics:

- Writing a signal synchronously propagates to dependents before the
  setter returns (outside an explicit :func:`batch`).
- Memos are **lazy**: they recompute only when read after a dependency
  changed, and they skip notifying their own observers when the
  recomputed value is unchanged (the glitch-free "equality short-circuit").
- Effects run in a second phase after pure computations have settled, so
  an effect never observes a half-updated graph.

Every reactive computation (effect, memo) is also **owned** by a parent
scope. When that scope re-runs or is disposed, all child computations are
torn down automatically, preventing leaks and giving lifecycle semantics
that match component mount/unmount boundaries.

Core types:

- [`Signal`][wybthon.Signal]: mutable reactive container.
- [`Owner`][wybthon.reactivity.Owner]: base ownership scope (cleanups + children).
- [`Computation`][wybthon.reactivity.Computation]: a reactive computation
  (effect or memo) that is itself an ownership scope.
- [`Resource`][wybthon.Resource]: async data wrapper with `data`/`error`/`loading`.

Public primitives:

- [`create_signal`][wybthon.create_signal]: create a `(getter, setter)` pair.
- [`create_effect`][wybthon.create_effect]: auto-tracking side-effect.
- [`create_memo`][wybthon.create_memo]: auto-tracking derived value.
- [`on_mount`][wybthon.on_mount] / [`on_cleanup`][wybthon.on_cleanup]:
  lifecycle hooks.
- [`batch`][wybthon.batch] / [`untrack`][wybthon.untrack]: scheduling control.
- [`create_root`][wybthon.create_root]: spawn an independent reactive root.
- [`merge_props`][wybthon.merge_props] / [`split_props`][wybthon.split_props]:
  prop composition helpers.
- [`map_array`][wybthon.map_array] / [`index_array`][wybthon.index_array] /
  [`create_selector`][wybthon.create_selector]: reactive list primitives.

Example:
    A counter with a derived doubled value::

        from wybthon import create_signal, create_memo, create_effect

        count, set_count = create_signal(0)
        doubled = create_memo(lambda: count() * 2)
        create_effect(lambda: print("doubled:", doubled()))

        set_count(2)  # synchronously prints "doubled: 4"
"""

from __future__ import annotations

import weakref
from collections.abc import Awaitable as AbcAwaitable
from typing import Any, Awaitable, Callable, Dict, Generic, List, Optional, Set, Tuple, TypeVar, Union, cast

__all__ = [
    "Owner",
    "Computation",
    "Signal",
    "Computed",
    "ReactiveProps",
    "batch",
    "Resource",
    "create_resource",
    "create_signal",
    "create_effect",
    "create_render_effect",
    "create_computed",
    "create_deferred",
    "create_memo",
    "create_unique_id",
    "catch_error",
    "on_mount",
    "on_cleanup",
    "untrack",
    "on",
    "create_root",
    "get_owner",
    "run_with_owner",
    "get_props",
    "children",
    "merge_props",
    "split_props",
    "map_array",
    "index_array",
    "create_selector",
]

T = TypeVar("T")

_DEFAULT_EQUALS = object()
_MISSING = object()

# The DOM command buffer's commit function. Effects emit batched DOM ops;
# committing at the end of each flush ships them across the bridge in one
# crossing. A no-op when the buffer is empty (e.g. pure-CPython usage).
from .kernel import commit as _kernel_commit  # noqa: E402

# ---------------------------------------------------------------------------
# Reactive node states (graph coloring)
#
# The scheduler is a push-mark / pull-recompute graph (the "reactively"
# algorithm, also used by modern SolidJS):
#
# - ``CLEAN``: value is current.
# - ``CHECK``: a *transitive* source may have changed; resolve sources
#   before deciding whether to recompute.
# - ``DIRTY``: a *direct* source definitely changed; must recompute.
# ---------------------------------------------------------------------------

_CLEAN = 0
_CHECK = 1
_DIRTY = 2

# Safety valve: the maximum number of effect runs in a single flush before
# we assume a runaway cyclic update and bail out (instead of hanging).
_MAX_FLUSH_ITER = 100000

# ---------------------------------------------------------------------------
# Global reactive state
# ---------------------------------------------------------------------------

_current_owner: Optional["Owner"] = None
_current_observer: Optional["Computation"] = None

# Effects pending execution in the current flush. Pure computations (memos)
# are *not* queued; they recompute lazily on read. Render effects (created
# by ``create_render_effect`` / ``create_computed``) run in an earlier
# phase than user effects, matching SolidJS's update ordering.
_render_effect_queue: List["Computation"] = []
_effect_queue: List["Computation"] = []
_running_effects: bool = False
_batch_depth: int = 0

# Re-entrant counter incremented while inside :func:`untrack`.  Used by
# the dev-mode "destructured prop" warning to detect intentional
# untracked reads and stay quiet.
_untrack_depth: int = 0


def _is_inside_untrack() -> bool:
    """Return True when the current call stack is inside `untrack`."""
    return _untrack_depth > 0


def _has_current_computation() -> bool:
    """Return True when there's an active reactive computation (effect/memo).

    Used by the dev-mode "destructured prop" warning to suppress noise when a
    prop accessor is read inside an effect / memo body during setup; those
    are the canonical "subscribe to this prop" patterns, not the footgun the
    warning is trying to flag.
    """
    return _current_observer is not None


def _changed(equals: Any, old: Any, new: Any) -> bool:
    """Return True when `new` should be considered a change from `old`.

    Implements the `equals` policy shared by signals and memos:

    - `equals=False`: always changed (notify on every write).
    - callable `equals`: changed when `equals(old, new)` is falsy.
    - default / `equals=True`: value equality with an identity fast-path
      (`is` first, then `==`).
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


# ---------------------------------------------------------------------------
# Synchronous flush
# ---------------------------------------------------------------------------


def _run_effects_if_idle() -> None:
    """Flush the effect queue unless we're batching or already flushing."""
    if _batch_depth == 0 and not _running_effects:
        _flush_effects()


def _flush_effects() -> None:
    """Run all queued effects to completion (the "effects" phase).

    Render effects (``create_render_effect`` / ``create_computed``) are
    drained before user effects, and re-drained whenever a user effect
    writes a signal, so user effects always observe DOM/render state
    that has settled. Effects pull their dependencies via
    ``_update_if_necessary`` so they always observe a fully-settled
    graph. Effects enqueued *during* the flush (because an effect wrote
    a signal) are drained in the same loop, giving synchronous settling
    within one logical update.
    """
    global _running_effects
    if _running_effects:
        return
    _running_effects = True
    try:
        ri = 0
        ei = 0
        guard = 0
        render_queue = _render_effect_queue
        queue = _effect_queue
        while ri < len(render_queue) or ei < len(queue):
            guard += 1
            if guard > _MAX_FLUSH_ITER:
                raise RuntimeError(
                    "Wybthon: reactive update did not stabilize " "(possible cyclic effect writing its own dependency)."
                )
            if ri < len(render_queue):
                comp = render_queue[ri]
                ri += 1
            else:
                comp = queue[ei]
                ei += 1
            if not comp._disposed:
                comp._update_if_necessary()
    finally:
        _render_effect_queue.clear()
        _effect_queue.clear()
        _running_effects = False
    # Ship every DOM op the flush produced across the bridge in one batch.
    _kernel_commit()


# ---------------------------------------------------------------------------
# Owner -- base ownership scope
# ---------------------------------------------------------------------------


class Owner:
    """Base reactive ownership scope.

    Tracks child owners and cleanup callbacks. When disposed, children are
    disposed first (depth-first), then this owner's own cleanups run. This
    mirrors SolidJS's ownership model.

    Attributes:
        _parent: Parent `Owner`, or `None` for roots.
        _children: Child owners, keyed by `id(child)` (insertion-ordered).
        _cleanups: Callbacks invoked LIFO during disposal.
        _disposed: True after `dispose()` has run; further calls are no-ops.
        _context_map: Lazily-allocated dict of context values stored at
            this owner (used by `Provider`).
        _error_handler: Optional callback receiving exceptions raised by
            descendant computations (installed by `ErrorBoundary` and
            [`catch_error`][wybthon.catch_error]).
    """

    __slots__ = ("_parent", "_children", "_cleanups", "_disposed", "_context_map", "_error_handler")

    def __init__(self) -> None:
        self._parent: Optional[Owner] = None
        # Keyed by ``id(child)`` so a child can detach itself in O(1) when
        # disposed individually (a ``For`` row leaving a 10k-row list would
        # otherwise pay a linear list.remove against its parent).
        self._children: Dict[int, Owner] = {}
        self._cleanups: List[Callable[[], Any]] = []
        self._disposed: bool = False
        self._context_map: Optional[Dict[Any, Any]] = None
        self._error_handler: Optional[Callable[..., Any]] = None

    def _add_child(self, child: "Owner") -> None:
        child._parent = self
        self._children[id(child)] = child

    def _dispose_children(self) -> None:
        if not self._children:
            return
        children = list(self._children.values())
        self._children.clear()
        for child in children:
            # Already detached wholesale above; skip the per-child pop.
            child._parent = None
            child.dispose()

    def _run_cleanups(self) -> None:
        while self._cleanups:
            fn = self._cleanups.pop()
            try:
                fn()
            except Exception:
                pass

    def _set_context(self, ctx_id: Any, value: Any) -> None:
        if self._context_map is None:
            self._context_map = {}
        self._context_map[ctx_id] = value

    def _lookup_context(self, ctx_id: Any, default: Any) -> Any:
        owner: Optional[Owner] = self
        while owner is not None:
            if owner._context_map is not None and ctx_id in owner._context_map:
                return owner._context_map[ctx_id]
            owner = owner._parent
        return default

    def dispose(self) -> None:
        """Tear down this owner and all descendants.

        Disposes children depth-first, then runs this owner's cleanup
        callbacks in LIFO order, and finally detaches from its parent.
        Subsequent calls are no-ops.
        """
        if self._disposed:
            return
        self._disposed = True
        self._dispose_children()
        self._run_cleanups()
        if self._parent is not None:
            self._parent._children.pop(id(self), None)
            self._parent = None


# ---------------------------------------------------------------------------
# Computation -- reactive computation (effect or memo), extends Owner
# ---------------------------------------------------------------------------


class Computation(Owner):
    """Reactive computation that tracks sources and re-runs when they change.

    A computation is either an **effect** (run for its side effects) or a
    **memo** (a lazily-recomputed derived value that other computations can
    observe). It is also an ownership scope: child computations created
    during execution are disposed before each re-run, preventing leaks from
    conditionally-created effects.

    Attributes:
        _fn: The callback executed by `_update()`.
        _sources: Sources (signals or memos) read during the last run.
        _state: One of `_CLEAN` / `_CHECK` / `_DIRTY`.
        _is_effect: True for effects (scheduled in the effects phase).
        _is_memo: True for memos (carry a value and observers).
    """

    __slots__ = (
        "_fn",
        "_sources",
        "_sources_set",
        "_state",
        "_is_effect",
        "_is_render",
        "_is_memo",
        "_value",
        "_observers",
        "_observer_set",
        "_equals",
    )

    def __init__(
        self,
        fn: Callable[[], Any],
        *,
        is_effect: bool = False,
        is_render: bool = False,
        is_memo: bool = False,
        value: Any = None,
        equals: Any = _DEFAULT_EQUALS,
    ) -> None:
        super().__init__()
        self._fn = fn
        self._sources: List[Any] = []
        self._sources_set: Set[Any] = set()
        self._state: int = _DIRTY
        self._is_effect = is_effect
        self._is_render = is_render
        self._is_memo = is_memo
        self._value: Any = value
        self._observers: List[Computation] = []
        self._observer_set: Set[Computation] = set()
        self._equals = equals

    # -- source side (memos act as sources for other computations) ----------

    def _add_observer(self, comp: "Computation") -> None:
        if comp not in self._observer_set:
            self._observer_set.add(comp)
            self._observers.append(comp)

    def _remove_observer(self, comp: "Computation") -> None:
        if comp in self._observer_set:
            self._observer_set.discard(comp)
            try:
                self._observers.remove(comp)
            except ValueError:
                pass

    # -- observer side -------------------------------------------------------

    def _add_source(self, source: Any) -> None:
        if source in self._sources_set:
            return
        self._sources_set.add(source)
        self._sources.append(source)
        source._add_observer(self)

    def _clear_sources(self) -> None:
        for src in self._sources:
            src._remove_observer(self)
        self._sources.clear()
        self._sources_set.clear()

    # -- scheduling ----------------------------------------------------------

    def _stale(self, state: int) -> None:
        """Mark this node stale (CHECK or DIRTY) and propagate to observers.

        On the first transition away from CLEAN we enqueue effects and push
        a CHECK marker to observers. Subsequent escalations (CHECK -> DIRTY)
        don't need to re-notify observers, which are already marked.
        """
        if self._disposed:
            return
        if self._state < state:
            was_clean = self._state == _CLEAN
            self._state = state
            if was_clean:
                if self._is_effect:
                    if self._is_render:
                        _render_effect_queue.append(self)
                    else:
                        _effect_queue.append(self)
                if self._observers:
                    for o in list(self._observers):
                        o._stale(_CHECK)

    def _update_if_necessary(self) -> None:
        """Bring this node up to date by pulling sources (glitch-free).

        The node is marked CLEAN *before* recomputing so that a write to one
        of its own dependencies made *during* the recompute (for example, an
        ``ErrorBoundary`` setting its error signal while mounting a throwing
        child) re-dirties it and schedules another run, rather than being
        swallowed. True cycles are bounded by the flush safety valve.
        """
        if self._disposed or self._state == _CLEAN:
            return
        if self._state == _CHECK:
            for src in list(self._sources):
                src._update_if_necessary()
                if self._state == _DIRTY:
                    break
        if self._state == _DIRTY:
            self._state = _CLEAN
            self._update()
        else:
            self._state = _CLEAN

    def _handle_error(self, exc: BaseException) -> bool:
        """Route `exc` to the nearest ancestor owner with an error handler.

        Returns True when a handler was found and invoked (the error is
        considered handled); False when the caller should re-raise.
        """
        owner: Optional[Owner] = self._parent
        while owner is not None:
            handler = owner._error_handler
            if handler is not None:
                try:
                    handler(exc)
                except Exception:
                    pass
                return True
            owner = owner._parent
        return False

    def _update(self) -> None:
        """Re-execute the tracked function, refreshing its dependency set.

        Disposes child owners and runs cleanups before each re-run so that
        conditional effects don't leak. The previous dependency edges are
        torn down and rebuilt while the body executes under this owner.

        Exceptions raised by effect bodies are routed to the nearest
        ancestor error handler (`ErrorBoundary` / `catch_error`); when no
        handler exists, the exception propagates to the caller.
        """
        if self._disposed:
            return
        self._dispose_children()
        self._run_cleanups()
        self._clear_sources()
        global _current_owner, _current_observer
        prev_owner = _current_owner
        prev_obs = _current_observer
        _current_owner = self
        _current_observer = self
        try:
            new_value = self._fn()
        except Exception as exc:
            if self._is_effect and self._handle_error(exc):
                return
            raise
        finally:
            _current_owner = prev_owner
            _current_observer = prev_obs
        if self._is_memo:
            if _changed(self._equals, self._value, new_value):
                self._value = new_value
                # A real value change escalates observers from CHECK to
                # DIRTY so they recompute; an unchanged value leaves them
                # CHECK (and they may resolve to CLEAN without work).
                for o in self._observers:
                    o._state = _DIRTY

    def _read(self) -> Any:
        """Read a memo's value: ensure it's current, then subscribe the reader."""
        self._update_if_necessary()
        obs = _current_observer
        if obs is not None and obs is not self and not self._disposed:
            obs._add_source(self)
        return self._value

    def dispose(self) -> None:
        """Dispose the computation and unsubscribe from all dependencies.

        Removes dependency edges, drops this node as a source for any of its
        observers, tears down child owners, and runs cleanups.
        """
        if self._disposed:
            return
        self._clear_sources()
        for o in list(self._observers):
            o._sources_set.discard(self)
            try:
                o._sources.remove(self)
            except ValueError:
                pass
        self._observers.clear()
        self._observer_set.clear()
        super().dispose()


# ---------------------------------------------------------------------------
# Signal
# ---------------------------------------------------------------------------


class Signal(Generic[T]):
    """Mutable reactive container that notifies observers on change.

    Most code uses [`create_signal`][wybthon.create_signal] which returns a
    `(getter, setter)` tuple instead of exposing `Signal` instances directly.
    This class is part of the public surface so `Signal[T]` can be used in
    type hints.

    Args:
        value: The initial value.
        equals: Equality policy. See [`create_signal`][wybthon.create_signal]
            for the full semantics.
    """

    def __init__(self, value: T, *, equals: Any = _DEFAULT_EQUALS) -> None:
        self._value: T = value
        self._observers: List[Computation] = []
        self._observer_set: Set[Computation] = set()
        self._equals = equals

    def _add_observer(self, comp: "Computation") -> None:
        if comp not in self._observer_set:
            self._observer_set.add(comp)
            self._observers.append(comp)

    def _remove_observer(self, comp: "Computation") -> None:
        if comp in self._observer_set:
            self._observer_set.discard(comp)
            try:
                self._observers.remove(comp)
            except ValueError:
                pass

    def _update_if_necessary(self) -> None:
        """Source-interface no-op; a signal's value is always current."""
        return

    def get(self) -> T:
        """Return the current value and subscribe the active computation.

        When called inside an effect, memo, or reactive hole, this signal
        is added to that computation's dependency set so it re-runs on
        future writes. Outside a tracking context the read is untracked.

        Returns:
            The current value held by the signal.
        """
        obs = _current_observer
        if obs is not None:
            obs._add_source(self)
        return self._value

    def peek(self) -> T:
        """Return the current value without subscribing the active computation."""
        return self._value

    def set(self, value: T) -> None:
        """Write a new value and synchronously notify observers if it changed.

        Equality is determined by the `equals` policy passed to the
        constructor (default: `is` then `==`, with `equals=False` to
        bypass the check entirely). Outside a [`batch`][wybthon.batch],
        dependent memos become readable immediately and effects run before
        this call returns.

        Args:
            value: The new value to store.
        """
        if not _changed(self._equals, self._value, value):
            return
        self._value = value
        observers = self._observers
        if observers:
            for o in list(observers):
                o._stale(_DIRTY)
            _run_effects_if_idle()


def signal(value: T) -> Signal[T]:
    """Create a new `Signal` with the given initial value.

    Most code should call [`create_signal`][wybthon.create_signal] instead;
    this function exists for low-level uses that need the raw `Signal`
    object (for example, attaching custom subscribers).

    Args:
        value: The initial value stored in the signal.

    Returns:
        A new `Signal[T]` with default equality semantics.
    """
    return Signal(value)


# ---------------------------------------------------------------------------
# ReactiveProps
# ---------------------------------------------------------------------------


class ReactiveProps:
    """Reactive proxy over a component's props dict.

    Every attribute or item access returns a **reactive accessor**: a
    zero-arg callable that returns the current value and tracks the read.
    This mirrors SolidJS's `props.x` semantics, adapted to Python.

    Access patterns:

    | Expression | Returns | Notes |
    |------------|---------|-------|
    | `props.name` | callable getter | Stable across reads. |
    | `props.name()` | current value | Tracked when called inside an effect or hole. |
    | `props["name"]` | callable getter | Same as `props.name`. |
    | `props.get("name", default)` | callable getter | Returns `default` when missing. |
    | `props.value("name", default)` | current value | One-shot snapshot, with auto-unwrap. |

    Embed the accessor directly in the VNode tree to create an automatic
    reactive hole; the surrounding DOM region updates only when the prop
    changes.

    Example:
        ```python
        @component
        def Greeting():
            props = get_props()
            # Auto-hole: only the text node updates when ``name`` changes.
            return p("Hello, ", props.name, "!")
        ```

    Note:
        `ReactiveProps` is read-only. Parents and the reconciler update it
        via the internal `_update` method.
    """

    __slots__ = ("_signals", "_getters", "_raw", "_defaults")

    def __init__(self, props: dict, defaults: Optional[Dict[str, Any]] = None) -> None:
        object.__setattr__(self, "_signals", {})
        object.__setattr__(self, "_getters", {})
        object.__setattr__(self, "_raw", dict(props))
        object.__setattr__(self, "_defaults", defaults or {})

    def _signal_for(self, key: str) -> "Signal[Any]":
        signals = object.__getattribute__(self, "_signals")
        sig = signals.get(key)
        if sig is None:
            raw = object.__getattribute__(self, "_raw")
            defaults = object.__getattribute__(self, "_defaults")
            value = raw.get(key, defaults.get(key))
            sig = Signal(value)
            signals[key] = sig
        return sig

    def _make_getter(self, key: str) -> Callable[[], Any]:
        """Return a stable, cached, callable accessor for `key`.

        The accessor reads the prop signal and, when the stored value is itself
        a getter (callable with no required args), transparently calls it. This
        means parents can pass either a static value (`count=5`) or a getter
        (`count=count_signal.get`, `count=lambda: total()`) and children always
        read the current value the same way: `props.count()`. Reactivity is
        tracked through both the prop signal and any underlying source.

        Args:
            key: Prop name to access.

        Returns:
            A zero-arg callable. Accessor identity is stable across calls
            so it can be embedded in VNode trees as a reactive hole.
        """
        getters = object.__getattribute__(self, "_getters")
        cached = getters.get(key)
        if cached is not None:
            return cached
        sig = self._signal_for(key)

        def accessor() -> Any:
            value = sig.get()
            if value is None:
                return None
            from .vnode import is_getter as _is_getter

            if callable(value) and _is_getter(value):
                return value()
            return value

        accessor._wyb_getter = True  # type: ignore[attr-defined]
        accessor.__name__ = f"<prop:{key}>"
        accessor.__qualname__ = accessor.__name__
        getters[key] = accessor
        return accessor

    def value(self, key: str, default: Any = _MISSING) -> Any:
        """Return the current value for `key` (tracked, with auto-unwrap).

        If the stored prop value is a getter, it's invoked and the result
        returned, mirroring `_make_getter`. If `default` is provided, it's
        returned when `key` is absent from both the props dict and the
        component's parameter defaults.

        Args:
            key: Prop name.
            default: Value returned when the key is missing. When omitted,
                missing keys yield `None`.

        Returns:
            The current prop value (auto-unwrapped if it's a getter).
        """
        signals = object.__getattribute__(self, "_signals")
        raw = object.__getattribute__(self, "_raw")
        defaults_map = object.__getattribute__(self, "_defaults")

        if key in signals or key in raw or key in defaults_map:
            return self._make_getter(key)()
        if default is _MISSING:
            return None
        return default

    def _update(self, new_props: dict) -> None:
        """Update props from parent (called by reconciler on re-render).

        All prop signals are written inside a single batch so a parent
        update flushes dependent holes exactly once.
        """
        signals = object.__getattribute__(self, "_signals")
        defaults = object.__getattribute__(self, "_defaults")
        object.__setattr__(self, "_raw", dict(new_props))
        with _Batch():
            for key, sig in signals.items():
                new_val = new_props.get(key, defaults.get(key))
                sig.set(new_val)

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            return object.__getattribute__(self, name)
        return self._make_getter(name)

    def __getitem__(self, key: str) -> Callable[[], Any]:
        return self._make_getter(key)

    def get(self, key: str, default: Any = None) -> Callable[[], Any]:
        """Return a callable getter for `key`, falling back to `default` if missing.

        When `key` exists on the prop bag (in raw props, prior signals, or
        component-parameter defaults), the returned getter reads the underlying
        signal: a tracking scope subscribes to it.

        When `key` is **missing**, the getter returns `default` on each call
        without creating a tracked signal. This means repeated `get(key, x)`
        / `get(key, y)` calls each return their own default (no sticky
        behavior). Components that need reactivity for a possibly-missing
        prop should declare it as a parameter with a default value;
        `@component` ensures a signal is created up front so future updates
        always propagate.

        Args:
            key: Prop name.
            default: Value returned by the fallback getter when `key` is
                missing.

        Returns:
            A zero-arg callable. Subscribers to a missing-key getter are
            **not** notified when the prop later appears.
        """
        defaults_map = object.__getattribute__(self, "_defaults")
        raw = object.__getattribute__(self, "_raw")
        signals = object.__getattribute__(self, "_signals")
        if key in signals or key in raw or key in defaults_map:
            return self._make_getter(key)

        def _default_getter() -> Any:
            return default

        _default_getter._wyb_getter = True  # type: ignore[attr-defined]
        _default_getter.__name__ = f"<prop:{key}:default>"
        return _default_getter

    def __contains__(self, key: Any) -> bool:
        raw = object.__getattribute__(self, "_raw")
        return key in raw

    def keys(self) -> Any:
        """Return the prop names currently set on this instance.

        The result reflects the latest props pushed into the proxy (it's
        not tracked as a reactive read).
        """
        raw = object.__getattribute__(self, "_raw")
        return raw.keys()

    def values(self) -> Any:
        """Return current prop values as a list (tracked)."""
        raw = object.__getattribute__(self, "_raw")
        return [self._signal_for(k).get() for k in raw]

    def items(self) -> Any:
        """Return `(key, current_value)` pairs (tracked)."""
        raw = object.__getattribute__(self, "_raw")
        return [(k, self._signal_for(k).get()) for k in raw]

    def __iter__(self) -> Any:
        raw = object.__getattribute__(self, "_raw")
        return iter(raw)

    def __len__(self) -> int:
        raw = object.__getattribute__(self, "_raw")
        return len(raw)

    def __repr__(self) -> str:
        raw = object.__getattribute__(self, "_raw")
        return f"ReactiveProps({raw!r})"

    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith("_"):
            object.__setattr__(self, name, value)
            return
        raise AttributeError("ReactiveProps is read-only. Props are updated by the parent component.")

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, dict):
            raw = object.__getattribute__(self, "_raw")
            return raw == other
        if isinstance(other, ReactiveProps):
            return object.__getattribute__(self, "_raw") == object.__getattribute__(other, "_raw")
        return NotImplemented

    def __hash__(self) -> int:
        return id(self)


# ---------------------------------------------------------------------------
# Computed (memo)
# ---------------------------------------------------------------------------


class _Computed(Generic[T]):
    """Read-only, lazily-recomputed signal derived from other signals.

    Backs [`create_memo`][wybthon.create_memo] and the public type
    alias `Computed`. The underlying `Computation` recomputes only when
    read after one of its tracked sources changed, and it notifies its own
    observers only when the recomputed value actually differs.
    """

    __slots__ = ("_comp",)

    def __init__(self, fn: Callable[[], T], *, equals: Any = _DEFAULT_EQUALS) -> None:
        comp = Computation(fn, is_memo=True, equals=equals)
        self._comp = comp
        if _current_owner is not None:
            _current_owner._add_child(comp)

    def get(self) -> T:
        return cast(T, self._comp._read())

    def dispose(self) -> None:
        self._comp.dispose()


# Public alias for the computed-value type. Users who want to type-hint a
# memoised value (for example, ``Computed[int]``) should reach for this name.
# The constructor lives at ``create_memo`` (returns a getter, not the class
# instance), but the type itself is part of the public surface.
Computed = _Computed


def computed(fn: Callable[[], T]) -> _Computed[T]:
    """Create a `_Computed` value derived from other signals.

    Low-level helper used by [`create_memo`][wybthon.create_memo]. Most
    code should use `create_memo` directly because it returns a plain
    getter (matching SolidJS's API).

    Args:
        fn: Zero-arg callable. Re-evaluated when any signal it reads
            changes.

    Returns:
        A `_Computed[T]` instance whose `.get()` returns the current value.
    """
    return _Computed(fn)


def effect(fn: Callable[[], Any]) -> Computation:
    """Run a reactive effect immediately and return its `Computation`.

    Low-level helper. Most code should use
    [`create_effect`][wybthon.create_effect] which additionally supports
    receiving the previous return value as an argument.

    Args:
        fn: Zero-arg callback. Re-runs when any signal it reads changes.

    Returns:
        The underlying `Computation`. Call `.dispose()` to stop the effect.
    """
    comp = Computation(fn, is_effect=True)
    if _current_owner is not None:
        _current_owner._add_child(comp)
    comp._update_if_necessary()
    return comp


def on_effect_cleanup(comp: Computation, fn: Callable[[], Any]) -> None:
    """Register `fn` to run when `comp` is disposed.

    Args:
        comp: The computation whose disposal should trigger the cleanup.
        fn: Zero-arg cleanup callback.
    """
    comp._cleanups.append(fn)


# ---------------------------------------------------------------------------
# Batch
# ---------------------------------------------------------------------------


class _Batch:
    """Context manager that batches signal updates into a single flush.

    Returned by [`batch()`][wybthon.batch] when called with no arguments.
    Increments a depth counter on `__enter__` and flushes pending
    effects exactly once when the outermost batch exits.
    """

    def __enter__(self) -> None:
        global _batch_depth
        _batch_depth += 1

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        global _batch_depth
        _batch_depth -= 1
        if _batch_depth == 0:
            _flush_effects()


def batch(fn: Optional[Callable[[], T]] = None) -> Union[T, _Batch]:
    """Batch signal updates so dependent effects flush once at the end.

    Two call shapes are supported:

    1. **Context manager** (Pythonic):
       ```python
       with batch():
           set_a(1)
           set_b(2)
       ```
    2. **Callback** (SolidJS style):
       ```python
       batch(lambda: (set_a(1), set_b(2)))
       ```

    When called with a function, the function's return value is returned.
    Effects are flushed synchronously when the outermost batch exits,
    matching SolidJS semantics.

    Args:
        fn: Optional zero-arg callable. When omitted, returns a context
            manager.

    Returns:
        Either a `_Batch` context manager (when `fn is None`) or the
        return value of `fn`.
    """
    if fn is None:
        return _Batch()
    global _batch_depth
    _batch_depth += 1
    try:
        result = fn()
    finally:
        _batch_depth -= 1
        if _batch_depth == 0:
            _flush_effects()
    return result


def untrack(fn: Callable[[], T]) -> T:
    """Run `fn` without tracking any signal reads.

    Useful inside effects when you need to read a signal without creating
    a dependency, or during component setup to seed local state from a
    prop without subscribing.

    Inside `untrack` the dev-mode destructured-prop warning is also
    silenced, so `count, set_count = create_signal(untrack(initial))`
    cleanly opts out of the noise.

    Args:
        fn: Zero-arg callable to invoke with tracking suppressed.

    Returns:
        Whatever `fn` returns.

    Example:
        ```python
        create_effect(lambda: print("a changed:", a(), "b is:", untrack(b)))
        ```
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


# ---------------------------------------------------------------------------
# Async resource
# ---------------------------------------------------------------------------

R = TypeVar("R")

FetchFn = Callable[..., Union[Awaitable[R], R]]

# Sentinel key under which ``Suspense`` stores its collector on the owner
# context map. Kept here (rather than in ``suspense.py``) so ``Resource``
# can look it up without importing browser-facing modules.
SUSPENSE_CONTEXT_KEY = "__wyb_suspense__"


class Resource(Generic[R]):
    """Async data accessor with reactive loading/error state.

    Matches SolidJS's resource shape: the resource **is** the accessor.
    Call it to read the current data (tracked); read `loading`, `error`,
    `latest`, and `state` as properties (also tracked).

    While a resource is in its initial `"pending"` state, reading it
    under a [`Suspense`][wybthon.Suspense] boundary automatically
    registers it with that boundary; no manual wiring is needed.
    Refetches (`"refreshing"` state) don't re-trigger Suspense; the
    previous data stays available, matching SolidJS.

    States:

    - `"unresolved"`: never fetched (source was `None`/`False`).
    - `"pending"`: first fetch in flight, no data yet.
    - `"ready"`: data available.
    - `"refreshing"`: refetch in flight, previous data still readable.
    - `"errored"`: last fetch raised.

    Example:
        ```python
        async def load_user(user_id, signal=None):
            resp = await fetch(f"/api/users/{user_id}")
            return await resp.json()

        user = create_resource(user_id, load_user)
        p("Name: ", span(lambda: (user() or {}).get("name", "...")))
        ```
    """

    def __init__(self, fetcher: FetchFn, source: Optional[Callable[[], Any]] = None) -> None:
        import asyncio
        import inspect

        self._asyncio = asyncio
        self._fetcher: FetchFn = fetcher
        self._source = source
        self._task: Optional[asyncio.Task[Any]] = None
        self._abort_controller: Any = None
        self._version: int = 0

        try:
            params = inspect.signature(fetcher).parameters
            self._fetcher_takes_signal = "signal" in params
            self._fetcher_takes_source = any(
                p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
                and p.name != "signal"
                for p in params.values()
            )
        except (ValueError, TypeError):
            self._fetcher_takes_signal = False
            self._fetcher_takes_source = False

        self._data: Signal[Optional[R]] = Signal(None)
        self._error: Signal[Optional[Any]] = Signal(None)
        self._loading: Signal[bool] = Signal(False)
        self._state: Signal[str] = Signal("unresolved")
        self._has_value: bool = False

        if source is None:
            self.refetch()
        else:
            self._setup_source_tracking()

    # -- reading ------------------------------------------------------------

    def __call__(self) -> Optional[R]:
        """Return the current data (tracked read).

        While the resource is `"pending"`, this registers it with the
        nearest enclosing [`Suspense`][wybthon.Suspense] boundary.
        """
        self._register_with_suspense()
        return self._data.get()

    @property
    def loading(self) -> bool:
        """`True` while a fetch is in flight (tracked read)."""
        return bool(self._loading.get())

    @property
    def error(self) -> Optional[Any]:
        """The most recent exception, or `None` (tracked read)."""
        return self._error.get()

    @property
    def latest(self) -> Optional[R]:
        """The most recent data, even while refreshing (tracked read).

        Unlike calling the resource, reading `latest` never registers
        with a Suspense boundary.
        """
        return self._data.get()

    @property
    def state(self) -> str:
        """The current lifecycle state string (tracked read)."""
        return self._state.get()

    def _register_with_suspense(self) -> None:
        if self._state.peek() != "pending":
            return
        owner = _current_owner
        if owner is None:
            return
        collector = owner._lookup_context(SUSPENSE_CONTEXT_KEY, None)
        if collector is not None:
            collector.register(self)

    # -- writing ------------------------------------------------------------

    def mutate(self, value: Union[R, Callable[[Optional[R]], R]]) -> Optional[R]:
        """Set the resource's data directly, without fetching.

        Supports functional updates like a signal setter. Clears any
        error and marks the resource `"ready"`.

        Args:
            value: The new data, or a callable receiving the current data.

        Returns:
            The stored value.
        """
        if callable(value):
            value = value(self._data.peek())
        with _Batch():
            self._has_value = True
            self._data.set(value)
            self._error.set(None)
            self._loading.set(False)
            self._state.set("ready")
        return self._data.peek()

    def _make_abort_controller(self) -> Any:
        try:
            from js import AbortController

            return AbortController.new()
        except Exception:
            return None

    def _setup_source_tracking(self) -> None:
        """Watch the `source` getter; fetch when it yields a usable value."""

        def watcher() -> None:
            assert self._source is not None
            value = self._source()
            if value is None or value is False:
                return
            self._refetch_with(value)

        effect(watcher)

    async def _run(self, current_version: int, controller: Any, source_value: Any) -> None:
        try:
            args: List[Any] = []
            kwargs: Dict[str, Any] = {}
            if self._fetcher_takes_source and self._source is not None:
                args.append(source_value)
            if self._fetcher_takes_signal:
                kwargs["signal"] = getattr(controller, "signal", None)
            coro_or_val = self._fetcher(*args, **kwargs)

            if isinstance(coro_or_val, AbcAwaitable):
                result = await coro_or_val
            else:
                result = cast(R, coro_or_val)

            if current_version == self._version:
                with _Batch():
                    self._has_value = True
                    self._error.set(None)
                    self._data.set(result)
                    self._loading.set(False)
                    self._state.set("ready")
        except Exception as e:
            if current_version != self._version:
                return
            with _Batch():
                self._error.set(e)
                self._loading.set(False)
                self._state.set("errored")

    def refetch(self) -> None:
        """Cancel any in-flight request and start a new fetch.

        The resource enters `"pending"` (first fetch) or `"refreshing"`
        (data already present). Older in-flight tasks are ignored when
        they resolve.
        """
        source_value = untrack(self._source) if self._source is not None else None
        self._refetch_with(source_value)

    def _refetch_with(self, source_value: Any) -> None:
        self.cancel()
        self._version += 1
        with _Batch():
            self._loading.set(True)
            self._error.set(None)
            self._state.set("refreshing" if self._has_value else "pending")

        controller = self._make_abort_controller()
        self._abort_controller = controller
        version = self._version

        async def runner() -> None:
            await self._run(version, controller, source_value)

        try:
            self._task = self._asyncio.create_task(runner())
        except Exception:
            self._asyncio.get_event_loop().create_task(runner())

    def cancel(self) -> None:
        """Abort the current in-flight fetch, if any.

        Calls `AbortController.abort()` on the wrapped browser controller,
        cancels the asyncio task, and resets `loading` to `False` without
        touching the data or error state.
        """
        self._version += 1
        try:
            if self._abort_controller is not None:
                self._abort_controller.abort()
        except Exception:
            pass
        self._abort_controller = None
        try:
            if self._task is not None:
                self._task.cancel()
        except Exception:
            pass
        self._task = None
        try:
            if self._loading.peek():
                with _Batch():
                    self._loading.set(False)
                    self._state.set("ready" if self._has_value else "unresolved")
        except Exception:
            pass


def create_resource(
    source_or_fetcher: Union[Callable[[], Any], Callable[..., Awaitable[R]]],
    fetcher: Optional[Callable[..., Awaitable[R]]] = None,
) -> Resource[R]:
    """Create an async [`Resource`][wybthon.Resource] accessor.

    Can be called two ways:

    - `create_resource(fetcher)`: simple fetcher, fetches immediately.
    - `create_resource(source, fetcher)`: fetches whenever the `source`
      getter's tracked value changes; when the source yields `None` or
      `False` the fetch is skipped (the resource stays unresolved).

    The fetcher may be sync or async. When it declares a positional
    parameter, the current source value is passed as the first argument.
    When it accepts a `signal` keyword argument, an `AbortSignal` is
    passed for cancellation support in the browser.

    Args:
        source_or_fetcher: When called with one argument, this is the
            fetcher. When called with two, this is the source getter
            (typically a signal accessor).
        fetcher: Optional fetcher. Required when `source_or_fetcher` is a
            source getter.

    Returns:
        A `Resource[R]`. Call it to read the data; read `.loading`,
        `.error`, `.latest`, and `.state` for the surrounding UI state.

    Example:
        ```python
        user_id, set_user_id = create_signal(1)

        async def load_user(uid, signal=None):
            resp = await fetch(f"/api/users/{uid}")
            return await resp.json()

        user = create_resource(user_id, load_user)
        ```
    """
    if fetcher is None:
        return Resource(source_or_fetcher)
    return Resource(fetcher, source=source_or_fetcher)


# ---------------------------------------------------------------------------
# Component context
# ---------------------------------------------------------------------------


class _ComponentContext(Owner):
    """Per-component-instance ownership scope.

    Created by the reconciler when a `@component` is mounted. Tracks
    lifecycle callbacks (`on_mount`), reactive prop signals, and any
    `Provider` values published by this component. Extends `Owner` so
    effects created during setup are automatically disposed when the
    component unmounts.
    """

    __slots__ = (
        "_mount_callbacks",
        "_props",
        "_reactive_props",
        "_vnode",
        "_provider_value_signals",
    )

    def __init__(self) -> None:
        super().__init__()
        self._mount_callbacks: List[Callable[[], Any]] = []
        self._props: dict = {}
        self._reactive_props: Optional[ReactiveProps] = None
        self._vnode: Any = None
        # Maps ``Context.id -> Signal`` for any contexts this component
        # provides via ``Provider``.  Used by the reconciler to update
        # the context value reactively without re-mounting subtrees.
        self._provider_value_signals: Optional[Dict[int, "Signal[Any]"]] = None

    def _run_mount_callbacks(self) -> None:
        for fn in self._mount_callbacks:
            try:
                fn()
            except Exception:
                pass
        self._mount_callbacks.clear()


# ---------------------------------------------------------------------------
# Owner tracking helpers
# ---------------------------------------------------------------------------


def _get_owner() -> Optional[Owner]:
    """Return the current reactive owner, if any (internal alias)."""
    return _current_owner


def _get_component_ctx() -> Optional[_ComponentContext]:
    """Walk up the ownership chain to find the nearest `_ComponentContext`."""
    owner = _current_owner
    while owner is not None:
        if isinstance(owner, _ComponentContext):
            return owner
        owner = owner._parent
    return None


def get_owner() -> Optional[Owner]:
    """Return the current reactive owner scope, if any.

    Capture the owner before crossing async boundaries (e.g., `await`) and
    restore it with [`run_with_owner`][wybthon.run_with_owner] to maintain
    proper lifecycle management.

    Returns:
        The active `Owner`, or `None` when called outside any reactive
        scope.
    """
    return _current_owner


def run_with_owner(owner: Optional[Owner], fn: Callable[[], T]) -> T:
    """Run `fn` under the given ownership scope.

    Useful for restoring context after an `await` boundary where the
    reactive owner would otherwise be lost.

    Args:
        owner: The owner to install for the duration of `fn`. Pass `None`
            to disable ownership tracking entirely.
        fn: Zero-arg callable to execute.

    Returns:
        Whatever `fn` returns.

    Example:
        ```python
        async def load():
            owner = get_owner()
            data = await fetch_something()
            run_with_owner(owner, lambda: create_effect(lambda: use(data)))
        ```
    """
    global _current_owner
    prev = _current_owner
    _current_owner = owner
    try:
        return fn()
    finally:
        _current_owner = prev


# ---------------------------------------------------------------------------
# Public primitives
# ---------------------------------------------------------------------------


def create_signal(value: T, *, equals: Any = _DEFAULT_EQUALS) -> tuple:
    """Create a reactive signal and return `(getter, setter)`.

    Works inside or outside components. Inside a stateful component the
    signal is captured by the render function's closure and persists
    naturally; there's no cursor system or "rules of hooks".

    The setter supports **functional updates**, matching SolidJS: when
    called with a callable, the callable receives the current value and
    its return value becomes the new value. To *store* a callable as the
    signal's value, wrap it: `set_fn(lambda _prev: my_callable)`.

    Args:
        value: Initial value stored in the signal.
        equals: Equality policy controlling when subscribers are notified.
            Accepts:

            - The default sentinel (or `True`): **value equality** (`new == old`)
              with an identity fast-path. Skips notification when the new
              value is `is`-identical *or* `==`-equal to the old. This
              matches Python's natural intuition; re-setting an unchanged
              value is a no-op, and a fresh container with equal contents
              also skips notification.
            - `False`: always notify on every `set()` call, even when the
              new value is identical or equal to the old. Useful for
              "fire a change event" signals.
            - A callable `(old, new) -> bool`: skip notification when it
              returns `True`. Pass `equals=lambda a, b: a is b` for
              SolidJS-style identity-only semantics.

    Returns:
        A `(getter, setter)` tuple. The getter is a zero-arg callable
        suitable for embedding as a reactive hole. The setter returns
        the value that was stored.

    Example:
        ```python
        count, set_count = create_signal(0)
        print(count())              # 0
        set_count(5)
        print(count())              # 5
        set_count(lambda c: c + 1)  # functional update
        print(count())              # 6
        ```
    """
    sig: Signal[Any] = Signal(value, equals=equals)

    def setter(new_value: Any) -> Any:
        if callable(new_value):
            new_value = new_value(sig._value)
        sig.set(new_value)
        return sig._value

    return sig.get, setter


# Cache of "does fn accept a previous-value positional arg" results, keyed
# weakly so short-lived lambdas don't pin memory or recycle ids.
_accepts_prev_cache: "weakref.WeakKeyDictionary[Any, bool]" = weakref.WeakKeyDictionary()


def _accepts_prev_arg(fn: Callable[..., Any]) -> bool:
    """Return True when `fn` declares a required positional parameter.

    `inspect.signature` is expensive and effects are created in hot paths
    (holes, list rows), so results are cached per function object.
    """
    try:
        cached = _accepts_prev_cache.get(fn)
        if cached is not None:
            return cached
    except TypeError:
        cached = None
    import inspect as _inspect

    try:
        sig = _inspect.signature(fn)
        result = any(
            p.kind in (_inspect.Parameter.POSITIONAL_ONLY, _inspect.Parameter.POSITIONAL_OR_KEYWORD)
            and p.default is _inspect.Parameter.empty
            for p in sig.parameters.values()
        )
    except (ValueError, TypeError):
        result = False
    try:
        _accepts_prev_cache[fn] = result
    except TypeError:
        pass
    return result


def _create_effect_impl(fn: Callable[..., Any], *, is_render: bool) -> Computation:
    """Shared implementation for `create_effect` and `create_render_effect`."""
    if _accepts_prev_arg(fn):
        _prev: List[Any] = [None]

        def wrapped() -> None:
            _prev[0] = fn(_prev[0])

        body: Callable[[], Any] = wrapped
    else:
        body = fn

    comp = Computation(body, is_effect=True, is_render=is_render)
    if _current_owner is not None:
        _current_owner._add_child(comp)
    comp._update_if_necessary()
    return comp


def create_effect(fn: Callable[..., Any]) -> Computation:
    """Create an auto-tracking reactive effect.

    The effect runs immediately and re-runs whenever any signal read inside
    `fn` changes. [`on_cleanup`][wybthon.on_cleanup] may be called inside
    `fn` to register per-run cleanup that runs before re-execution and on
    disposal.

    If `fn` accepts a positional parameter, the **previous return value**
    is passed on each re-execution (`None` on the first run), matching
    SolidJS's `createEffect(prev => ...)`.

    Inside a component, the effect is automatically disposed on unmount.

    Args:
        fn: Zero- or one-arg callable. When it accepts an argument, the
            previous return value is forwarded.

    Returns:
        The underlying `Computation`. Call `.dispose()` to stop the effect
        manually.

    Example:
        ```python
        count, set_count = create_signal(0)
        create_effect(lambda prev: (print("was", prev), count())[1])
        ```
    """
    return _create_effect_impl(fn, is_render=False)


def create_render_effect(fn: Callable[..., Any]) -> Computation:
    """Create an effect that runs in the **render phase**, before user effects.

    Matches SolidJS's `createRenderEffect`: within one flush, all pending
    render effects execute before any [`create_effect`][wybthon.create_effect]
    callbacks. Wybthon's internal reactive holes and prop bindings run in
    this phase, so a render effect observes the DOM in the same state the
    framework's own bindings do.

    Args:
        fn: Zero- or one-arg callable (the previous return value is
            forwarded when accepted, as with `create_effect`).

    Returns:
        The underlying `Computation`.
    """
    return _create_effect_impl(fn, is_render=True)


def create_computed(fn: Callable[..., Any]) -> Computation:
    """Create an eagerly-run computation in the pure (pre-render) phase.

    Matches SolidJS's `createComputed`: use it to derive state by writing
    other signals *before* rendering happens. Prefer
    [`create_memo`][wybthon.create_memo] for plain derived values; reach
    for `create_computed` only when you must push a value into another
    signal.

    Args:
        fn: Zero- or one-arg callable.

    Returns:
        The underlying `Computation`.
    """
    return _create_effect_impl(fn, is_render=True)


_unique_id_counter: int = 0


def create_unique_id() -> str:
    """Return a process-unique id string (e.g., for `for`/`id` attribute pairs).

    Matches SolidJS's `createUniqueId`.

    Returns:
        A short unique string like `"wyb-7"`.
    """
    global _unique_id_counter
    _unique_id_counter += 1
    return f"wyb-{_unique_id_counter}"


def catch_error(fn: Callable[[], T], handler: Callable[[Any], Any]) -> Optional[T]:
    """Run `fn` with an error handler, catching errors thrown now or later.

    Matches SolidJS's `catchError`. The handler receives exceptions
    raised synchronously by `fn` **and** exceptions raised later by any
    effect created inside `fn` (they route up the ownership tree to the
    nearest handler).

    Args:
        fn: Zero-arg callable to execute under the error scope.
        handler: Callback receiving the exception.

    Returns:
        The return value of `fn`, or `None` when `fn` raised.

    Example:
        ```python
        result = catch_error(lambda: risky_setup(), lambda e: report(e))
        ```
    """
    scope = Owner()
    scope._error_handler = handler
    global _current_owner
    if _current_owner is not None:
        _current_owner._add_child(scope)
    prev = _current_owner
    _current_owner = scope
    try:
        return fn()
    except Exception as exc:
        try:
            handler(exc)
        except Exception:
            pass
        return None
    finally:
        _current_owner = prev


def create_deferred(source: Callable[[], T]) -> Callable[[], T]:
    """Return a getter that trails `source`, updating on the next event-loop tick.

    A lightweight analogue of SolidJS's `createDeferred`: reads of the
    returned getter don't recompute synchronously when `source` changes;
    instead, the new value is published asynchronously (via the running
    asyncio loop when one exists, else immediately). Use it to decouple
    expensive consumers from rapid-fire updates.

    Args:
        source: Zero-arg tracked getter.

    Returns:
        A zero-arg getter for the deferred value.
    """
    deferred: Signal[Any] = Signal(untrack(source))
    pending: List[Any] = []

    def _publish() -> None:
        if pending:
            value = pending.pop()
            pending.clear()
            deferred.set(value)

    def _track() -> None:
        value = source()
        if not pending and value == deferred.peek():
            return
        pending.append(value)
        try:
            import asyncio

            loop = asyncio.get_running_loop()
            loop.call_soon(_publish)
        except Exception:
            _publish()

    _create_effect_impl(_track, is_render=False)
    return deferred.get


def create_memo(fn: Callable[[], T]) -> Callable[[], T]:
    """Create an auto-tracking computed value and return its getter.

    Re-computes lazily, only when read after a tracked source changed.
    Inside a component, the underlying computation is disposed on unmount.

    Args:
        fn: Zero-arg callable producing the derived value.

    Returns:
        A zero-arg callable. Reading it inside a tracking scope creates
        a dependency on the memoised value.

    Example:
        ```python
        doubled = create_memo(lambda: count() * 2)
        print(doubled())  # reactive read
        ```
    """
    c = _Computed(fn)
    return c.get


def on_mount(fn: Callable[[], Any]) -> None:
    """Register a callback to run once after the component mounts.

    Must be called during a component's setup phase (the body of a
    `@component` function, before the `return`).

    Args:
        fn: Zero-arg callback invoked once after the first render commits.

    Raises:
        RuntimeError: If called outside a component setup phase.
    """
    ctx = _get_component_ctx()
    if ctx is None:
        raise RuntimeError("on_mount() can only be called inside a component's setup phase")
    ctx._mount_callbacks.append(fn)


def on_cleanup(fn: Callable[[], Any]) -> None:
    """Register a cleanup callback on the active reactive owner.

    Lifecycle differs by call site:

    - Inside [`create_effect`][wybthon.create_effect]: runs before each
      re-execution and on final disposal.
    - Inside a component's setup phase: runs when the component unmounts.
    - Inside a reactive hole: runs before each hole re-evaluation and
      when the hole is disposed.

    Args:
        fn: Zero-arg cleanup callback.

    Raises:
        RuntimeError: If called outside any reactive scope.
    """
    if _current_owner is not None:
        _current_owner._cleanups.append(fn)
    else:
        raise RuntimeError("on_cleanup() must be called inside a component or create_effect()")


def children(fn: Callable[[], Any]) -> Callable[[], List[Any]]:
    """Resolve and memoize reactive children, returning a memo getter.

    Wraps a getter that returns children (e.g., `lambda: props.children()`)
    and returns a memo that flattens nested lists and unwraps callables.
    Matches SolidJS's `children()` helper.

    Args:
        fn: Zero-arg getter that returns the raw children value
            (typically `lambda: get_props().children()`).

    Returns:
        A zero-arg memo getter producing a flat list of resolved children.

    Example:
        ```python
        @component
        def Card(title=""):
            props = get_props()
            resolved = children(lambda: props.children())
            return section(h3(props.title), *resolved())
        ```
    """

    def _resolve(val: Any) -> List[Any]:
        if val is None:
            return []
        if isinstance(val, (list, tuple)):
            out: List[Any] = []
            for item in val:
                out.extend(_resolve(item))
            return out
        return [val]

    return create_memo(lambda: _resolve(fn()))


def get_props() -> "ReactiveProps":
    """Return the [`ReactiveProps`][wybthon.ReactiveProps] proxy for the current component.

    The returned object provides reactive access to individual props. Each
    attribute / index lookup yields a callable getter; call the getter to
    read the current value (tracked when called inside an effect or hole).

    Most components should rely on the destructured parameters provided
    by `@component`. Use `get_props()` for advanced cases such as generic
    wrappers, key iteration, or proxy-mode interop.

    Returns:
        The cached `ReactiveProps` proxy for this component instance.

    Raises:
        RuntimeError: If called outside a component setup phase.

    Example:
        ```python
        @component
        def Greet(name="world"):
            # ``name`` is already a reactive accessor.
            return p("Hello, ", name, "!")

        @component
        def Advanced():
            props = get_props()
            create_effect(lambda: print("name:", props.name()))
        ```
    """
    ctx = _get_component_ctx()
    if ctx is None:
        raise RuntimeError("get_props() can only be called inside a component")
    if ctx._reactive_props is not None:
        return ctx._reactive_props
    rp = ReactiveProps(ctx._props)
    ctx._reactive_props = rp
    return rp


# ---------------------------------------------------------------------------
# Additional reactive utilities
# ---------------------------------------------------------------------------


def on(
    deps: Union[Callable[[], Any], List[Callable[[], Any]]],
    fn: Callable[..., Any],
    defer: bool = False,
) -> Computation:
    """Create an effect with explicit dependencies.

    `deps` may be a single getter or a list of getters. `fn` receives the
    current value(s) as positional arguments. Only the listed deps are
    tracked; the body of `fn` runs inside `untrack`.

    Args:
        deps: One getter or a list of getters to subscribe to.
        fn: Callback receiving the current dep value(s) on each change.
        defer: When `True`, skip the first invocation (so `fn` runs only
            on subsequent changes, not the initial read).

    Returns:
        The underlying `Computation`.

    Example:
        ```python
        on(count, lambda v: print("count is now", v))
        on([a, b], lambda va, vb: print(f"a={va}, b={vb}"), defer=True)
        ```
    """
    dep_list: List[Callable[[], Any]] = deps if isinstance(deps, list) else [deps]
    ran = [False]

    def tracked() -> None:
        values = [d() for d in dep_list]
        if defer and not ran[0]:
            ran[0] = True
            return
        ran[0] = True

        def call_fn() -> None:
            if len(values) == 1:
                fn(values[0])
            else:
                fn(*values)

        global _current_observer
        prev = _current_observer
        _current_observer = None
        try:
            call_fn()
        finally:
            _current_observer = prev

    return create_effect(tracked)


def create_root(fn: Callable[[Callable[[], None]], T]) -> T:
    """Run `fn` inside an independent reactive root.

    Useful for spawning long-lived reactive work that shouldn't be tied
    to the surrounding component's lifecycle (e.g., global stores).

    Args:
        fn: Callable receiving a `dispose` callback. Calling `dispose()`
            tears down the root and any effects created inside it.

    Returns:
        Whatever `fn` returns.

    Example:
        ```python
        result = create_root(lambda dispose: setup_global_state(dispose))
        ```
    """
    root = Owner()
    global _current_owner
    prev = _current_owner
    _current_owner = root
    try:

        def dispose() -> None:
            root.dispose()

        return fn(dispose)
    finally:
        _current_owner = prev


def _resolve_source(src: Any) -> Any:
    """Call `src` if it's a callable getter; otherwise return as-is."""
    if src is None:
        return None
    if callable(src) and not isinstance(src, dict):
        return src()
    return src


class _MergedProps:
    """Reactive merged-props proxy returned by [`merge_props`][wybthon.merge_props].

    Reading a key lazily checks sources right-to-left. When a source is a
    callable (e.g., a signal getter returning a dict), it's called on each
    access, so reads inside reactive computations are tracked automatically.
    """

    __slots__ = ("_sources",)

    def __init__(self, sources: List[Any]) -> None:
        object.__setattr__(self, "_sources", sources)

    def _resolve(self) -> dict:
        merged: dict = {}
        for src in object.__getattribute__(self, "_sources"):
            d = _resolve_source(src)
            if d is None:
                continue
            if isinstance(d, (_MergedProps, _SplitProps)):
                merged.update(dict(d.items()))
            elif hasattr(d, "items"):
                merged.update(d)
        return merged

    def __getitem__(self, key: str) -> Any:
        for src in reversed(object.__getattribute__(self, "_sources")):
            d = _resolve_source(src)
            if d is None:
                continue
            try:
                if key in d:
                    return d[key]
            except TypeError:
                continue
        raise KeyError(key)

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            return object.__getattribute__(self, name)
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name)

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default

    def keys(self) -> Any:
        return self._resolve().keys()

    def values(self) -> Any:
        return self._resolve().values()

    def items(self) -> Any:
        return self._resolve().items()

    def __contains__(self, key: Any) -> bool:
        for src in reversed(object.__getattribute__(self, "_sources")):
            d = _resolve_source(src)
            if d is None:
                continue
            try:
                if key in d:
                    return True
            except TypeError:
                continue
        return False

    def __iter__(self) -> Any:
        return iter(self._resolve())

    def __len__(self) -> int:
        return len(self._resolve())

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, dict):
            return self._resolve() == other
        if isinstance(other, (_MergedProps, _SplitProps)):
            return self._resolve() == other._resolve()
        return NotImplemented

    def __repr__(self) -> str:
        return f"MergedProps({self._resolve()!r})"

    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith("_"):
            object.__setattr__(self, name, value)
            return
        raise AttributeError("MergedProps is read-only")


class _SplitProps:
    """Reactive split-props proxy returned by [`split_props`][wybthon.split_props].

    Filters a source's keys by inclusion or exclusion. Reads forward to the
    underlying source, so callable sources continue to participate in
    reactive tracking.
    """

    __slots__ = ("_source", "_keys", "_exclude")

    def __init__(
        self,
        source: Any,
        keys: Optional[Set[str]] = None,
        exclude: Optional[Set[str]] = None,
    ) -> None:
        object.__setattr__(self, "_source", source)
        object.__setattr__(self, "_keys", frozenset(keys) if keys else None)
        object.__setattr__(self, "_exclude", frozenset(exclude) if exclude else None)

    def _get_source(self) -> Any:
        src = object.__getattribute__(self, "_source")
        return _resolve_source(src)

    def _included(self, key: str) -> bool:
        keys = object.__getattribute__(self, "_keys")
        exclude = object.__getattribute__(self, "_exclude")
        if keys is not None:
            return key in keys
        if exclude is not None:
            return key not in exclude
        return True

    def _resolve(self) -> dict:
        d = self._get_source()
        if d is None:
            return {}
        if isinstance(d, (_MergedProps, _SplitProps)):
            return {k: v for k, v in d.items() if self._included(k)}
        if hasattr(d, "items"):
            return {k: v for k, v in d.items() if self._included(k)}
        return {}

    def __getitem__(self, key: str) -> Any:
        if not self._included(key):
            raise KeyError(key)
        d = self._get_source()
        if d is not None and key in d:
            return d[key]
        raise KeyError(key)

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            return object.__getattribute__(self, name)
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name)

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default

    def keys(self) -> Any:
        return self._resolve().keys()

    def values(self) -> Any:
        return self._resolve().values()

    def items(self) -> Any:
        return self._resolve().items()

    def __contains__(self, key: Any) -> bool:
        if not self._included(key):
            return False
        d = self._get_source()
        return d is not None and key in d

    def __iter__(self) -> Any:
        return iter(self._resolve())

    def __len__(self) -> int:
        return len(self._resolve())

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, dict):
            return self._resolve() == other
        if isinstance(other, (_MergedProps, _SplitProps)):
            return self._resolve() == other._resolve()
        return NotImplemented

    def __repr__(self) -> str:
        return f"SplitProps({self._resolve()!r})"

    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith("_"):
            object.__setattr__(self, name, value)
            return
        raise AttributeError("SplitProps is read-only")


def merge_props(*sources: Any) -> "_MergedProps":
    """Merge multiple prop sources into a reactive proxy.

    Each source may be a plain `dict`, a zero-arg getter that returns a
    dict, or another `_MergedProps` / `_SplitProps`. Later sources
    override earlier ones on key conflicts.

    The returned object supports dict-like access (`[]`, `.get`, `in`,
    iteration). When a source is a callable, it's called on each property
    access, so signal reads inside the getter are tracked by the current
    reactive computation.

    Args:
        *sources: One or more prop sources, in priority order
            (rightmost wins).

    Returns:
        A reactive merged-props proxy.

    Example:
        ```python
        defaults = {"size": "md", "variant": "solid"}
        final = merge_props(defaults, props)
        # final["size"] lazily reads from props, then falls back to defaults
        ```
    """
    return _MergedProps(list(sources))


def split_props(
    props: Any,
    *key_groups: List[str],
) -> Tuple[Any, ...]:
    """Split a props source into groups by key name, plus a rest group.

    Args:
        props: A `dict`, callable getter, or `_MergedProps` / `_SplitProps`
            to split.
        *key_groups: One or more lists of keys defining each group.

    Returns:
        A tuple `(group1, group2, ..., rest)` where each group is a
        reactive proxy that lazily reads from the original `props`. The
        final `rest` group contains every key not claimed by an earlier
        group.

    Example:
        ```python
        local, rest = split_props(props, ["class", "style"])
        # local["class"] lazily reads from props
        # rest contains every other key
        ```
    """
    results: List[Any] = []
    claimed: set = set()
    for group in key_groups:
        group_set = set(group)
        claimed |= group_set
        results.append(_SplitProps(props, keys=group_set))
    results.append(_SplitProps(props, exclude=claimed))
    return tuple(results)


# ---------------------------------------------------------------------------
# Reactive list mapping primitives
# ---------------------------------------------------------------------------

_map_key_counter: int = 0


def _run_owned_untracked(owner: "Owner", fn: Callable[[], T]) -> T:
    """Run `fn` owned by `owner` with signal tracking suppressed.

    Used by the list primitives so a per-item mapping body owns the
    computations it creates (for correct disposal) while not subscribing
    the surrounding list computation to the item's reads.
    """
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


def map_array(
    source: Callable[[], Optional[List[Any]]],
    map_fn: Callable[[Callable[[], Any], Callable[[], int]], T],
) -> Callable[[], List[T]]:
    """Map a reactive list with stable per-item scopes (keyed by identity).

    Items are matched by **reference identity**. The mapping callback
    runs **once** per unique item; when an item leaves the source list,
    its reactive scope is disposed automatically.

    Args:
        source: Zero-arg getter that returns the current list (typically
            a signal accessor).
        map_fn: Called as `map_fn(item_getter, index_getter)` for each
            unique item. `item_getter()` returns the item; `index_getter()`
            returns its current position.

    Returns:
        A zero-arg getter producing the mapped list. Reading it inside a
        reactive scope subscribes to source changes.

    Example:
        ```python
        items, set_items = create_signal(["A", "B", "C"])
        labels = map_array(items, lambda item, idx: f"{idx()}: {item()}")
        # labels() == ["0: A", "1: B", "2: C"]
        ```
    """
    global _map_key_counter
    _parent = _current_owner
    _cache: List[Dict[str, Any]] = []

    def _compute() -> List[T]:
        global _map_key_counter
        items = source()
        if not items:
            for entry in _cache:
                entry["owner"].dispose()
            _cache.clear()
            return []

        new_cache: List[Dict[str, Any]] = []
        used = [False] * len(_cache)

        # Identity index: id(item) -> cache positions, consumed in order
        # so duplicate items resolve stably. Keeps matching O(n).
        by_id: Dict[int, List[int]] = {}
        for ci in range(len(_cache)):
            by_id.setdefault(id(_cache[ci]["item"]), []).append(ci)
        by_id_pos: Dict[int, int] = {}

        for idx, item in enumerate(items):
            found = -1
            positions = by_id.get(id(item))
            if positions is not None:
                p = by_id_pos.get(id(item), 0)
                while p < len(positions) and used[positions[p]]:
                    p += 1
                by_id_pos[id(item)] = p
                if p < len(positions):
                    found = positions[p]
                    by_id_pos[id(item)] = p + 1

            if found >= 0:
                used[found] = True
                entry = _cache[found]
                entry["index_signal"].set(idx)
                new_cache.append(entry)
            else:
                owner = Owner()
                if _parent is not None:
                    _parent._add_child(owner)

                item_sig: Signal[Any] = Signal(item)
                idx_sig: Signal[int] = Signal(idx)

                result = _run_owned_untracked(owner, lambda: map_fn(item_sig.get, idx_sig.get))

                _map_key_counter += 1
                new_cache.append(
                    {
                        "item": item,
                        "owner": owner,
                        "result": result,
                        "item_signal": item_sig,
                        "index_signal": idx_sig,
                        "key": _map_key_counter,
                    }
                )

        for ci in range(len(_cache)):
            if not used[ci]:
                _cache[ci]["owner"].dispose()

        _cache.clear()
        _cache.extend(new_cache)
        return [e["result"] for e in new_cache]

    return create_memo(_compute)


def index_array(
    source: Callable[[], Optional[List[Any]]],
    map_fn: Callable[[Callable[[], Any], int], T],
) -> Callable[[], List[T]]:
    """Map a reactive list with stable per-index scopes.

    Unlike [`map_array`][wybthon.map_array], scopes are keyed by **index
    position**. Each slot has a reactive `item_getter` signal that
    updates when the value at that index changes.

    Args:
        source: Zero-arg getter that returns the current list.
        map_fn: Called as `map_fn(item_getter, index)`. `item_getter()`
            returns the item; `index` is a plain `int` (not a getter).

    Returns:
        A zero-arg getter producing the mapped list.

    Example:
        ```python
        items, set_items = create_signal(["A", "B", "C"])
        labels = index_array(items, lambda item, idx: f"[{idx}] {item()}")
        # labels() == ["[0] A", "[1] B", "[2] C"]
        ```
    """
    _parent = _current_owner
    _slots: List[Dict[str, Any]] = []

    def _compute() -> List[T]:
        items = source()
        if not items:
            for slot in _slots:
                slot["owner"].dispose()
            _slots.clear()
            return []

        items_list = list(items)
        new_len = len(items_list)
        old_len = len(_slots)

        for i in range(min(old_len, new_len)):
            _slots[i]["item_signal"].set(items_list[i])

        if new_len > old_len:
            for i in range(old_len, new_len):
                owner = Owner()
                if _parent is not None:
                    _parent._add_child(owner)

                item_sig: Signal[Any] = Signal(items_list[i])

                # ``_run_owned_untracked`` calls the thunk synchronously within
                # this iteration, so closing over ``i``/``item_sig`` is safe.
                result = _run_owned_untracked(owner, lambda: map_fn(item_sig.get, i))

                _slots.append({"owner": owner, "result": result, "item_signal": item_sig})

        elif new_len < old_len:
            for slot in _slots[new_len:]:
                slot["owner"].dispose()
            del _slots[new_len:]

        return [s["result"] for s in _slots]

    return create_memo(_compute)


def create_selector(
    source: Callable[[], Any],
) -> Callable[[Any], bool]:
    """Create an `O(1)` selection signal.

    When `source()` changes, only computations that previously called the
    returned `is_selected(key)` with the **old** or **new** key are
    notified, instead of every subscriber re-running.

    Args:
        source: Zero-arg getter returning the currently-selected key.

    Returns:
        A function `is_selected(key) -> bool` that's reactive to
        selection changes.

    Example:
        ```python
        selected, set_selected = create_signal(1)
        is_selected = create_selector(selected)

        # Inside a For loop per item:
        create_effect(lambda: print("active:", is_selected(item_id)))
        ```
    """
    _subs: Dict[Any, Set["Computation"]] = {}
    _prev_key: List[Any] = [None]
    _first = [True]

    def _notify(key: Any) -> None:
        subs = _subs.get(key)
        if subs:
            for comp in list(subs):
                comp._stale(_DIRTY)

    def _tracker() -> None:
        new_key = source()
        old_key = _prev_key[0]
        _prev_key[0] = new_key

        if _first[0]:
            _first[0] = False
            return

        if old_key == new_key:
            return

        _notify(old_key)
        _notify(new_key)
        _run_effects_if_idle()

    effect(_tracker)

    def is_selected(key: Any) -> bool:
        obs = _current_observer
        if obs is not None:
            subs = _subs.get(key)
            if subs is None:
                subs = set()
                _subs[key] = subs
            if obs not in subs:
                subs.add(obs)
                # Unsubscribe when the computation re-runs or is disposed,
                # so the map holds only live subscribers (rows leaving a
                # list would otherwise accumulate forever).
                bucket = subs

                def _unsubscribe(comp: "Computation" = obs, key: Any = key) -> None:
                    bucket.discard(comp)
                    if not bucket and _subs.get(key) is bucket:
                        del _subs[key]

                obs._cleanups.append(_unsubscribe)
        return _prev_key[0] == key

    return is_selected
