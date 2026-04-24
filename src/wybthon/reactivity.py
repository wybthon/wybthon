"""Signal-based reactive primitives with an ownership tree.

This module is the heart of Wybthon's SolidJS-inspired reactivity. Every
reactive computation (effect, memo) is **owned** by a parent scope. When
that scope re-runs or is disposed, all child computations are torn down
automatically — preventing leaks and giving lifecycle semantics that
match component mount/unmount boundaries.

Core types:

- [`Signal`][wybthon.Signal]: mutable reactive container.
- [`Owner`][wybthon.reactivity.Owner]: base ownership scope (cleanups + children).
- [`Computation`][wybthon.reactivity.Computation]: a reactive computation
  that is itself an ownership scope.
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

        set_count(2)  # logs "doubled: 4" on the next microtask flush
"""

from __future__ import annotations

from collections import deque
from collections.abc import Awaitable as AbcAwaitable
from typing import Any, Awaitable, Callable, Deque, Dict, Generic, List, Optional, Set, Tuple, TypeVar, Union, cast

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
    "create_memo",
    "on_mount",
    "on_cleanup",
    "untrack",
    "on",
    "create_root",
    "get_owner",
    "run_with_owner",
    "get_props",
    "read_prop",
    "iter_prop_keys",
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

# ---------------------------------------------------------------------------
# Global reactive state
# ---------------------------------------------------------------------------

_current_owner: Optional["Owner"] = None
_current_computation: Optional["Computation"] = None

_pending_queue: Deque["Computation"] = deque()
_pending_set: Set["Computation"] = set()
_flush_scheduled: bool = False
_batch_depth: int = 0

# Re-entrant counter incremented while inside :func:`untrack`.  Used by
# the dev-mode "destructured prop" warning to detect intentional
# untracked reads and stay quiet.
_untrack_depth: int = 0


def _is_inside_untrack() -> bool:
    """Return True when the current call stack is inside `untrack`."""
    return _untrack_depth > 0


def _has_current_computation() -> bool:
    """Return True when there is an active reactive computation (effect/memo).

    Used by the dev-mode "destructured prop" warning to suppress noise when a
    prop accessor is read inside an effect / memo body during setup — those
    are the canonical "subscribe to this prop" patterns, not the footgun the
    warning is trying to flag.
    """
    return _current_computation is not None


# ---------------------------------------------------------------------------
# Microtask scheduling
# ---------------------------------------------------------------------------


def _schedule_flush() -> None:
    global _flush_scheduled
    if _flush_scheduled:
        return
    _flush_scheduled = True

    try:
        from js import queueMicrotask
        from pyodide.ffi import create_once_callable

        queueMicrotask(create_once_callable(lambda: _flush()))
    except Exception:  # pragma: no cover
        try:
            from js import setTimeout
            from pyodide.ffi import create_once_callable

            setTimeout(create_once_callable(lambda: _flush()), 0)
        except Exception:
            try:
                import threading

                threading.Timer(0, _flush).start()
            except Exception:
                _flush()


def _flush() -> None:
    global _flush_scheduled
    _flush_scheduled = False
    initial_count = len(_pending_queue)
    for _ in range(initial_count):
        comp = _pending_queue.popleft()
        if comp not in _pending_set:
            continue
        _pending_set.discard(comp)
        if not comp._disposed:
            comp.run()


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
        _children: List of child owners.
        _cleanups: Callbacks invoked LIFO during disposal.
        _disposed: True after `dispose()` has run; further calls are no-ops.
        _context_map: Lazily-allocated dict of context values stored at
            this owner (used by `Provider`).
    """

    __slots__ = ("_parent", "_children", "_cleanups", "_disposed", "_context_map")

    def __init__(self) -> None:
        self._parent: Optional[Owner] = None
        self._children: List[Owner] = []
        self._cleanups: List[Callable[[], Any]] = []
        self._disposed: bool = False
        self._context_map: Optional[Dict[int, Any]] = None

    def _add_child(self, child: "Owner") -> None:
        child._parent = self
        self._children.append(child)

    def _dispose_children(self) -> None:
        for child in list(self._children):
            child.dispose()
        self._children.clear()

    def _run_cleanups(self) -> None:
        while self._cleanups:
            fn = self._cleanups.pop()
            try:
                fn()
            except Exception:
                pass

    def _set_context(self, ctx_id: int, value: Any) -> None:
        if self._context_map is None:
            self._context_map = {}
        self._context_map[ctx_id] = value

    def _lookup_context(self, ctx_id: int, default: Any) -> Any:
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
            try:
                self._parent._children.remove(self)
            except ValueError:
                pass
            self._parent = None


# ---------------------------------------------------------------------------
# Computation -- reactive computation (extends Owner)
# ---------------------------------------------------------------------------


class Computation(Owner):
    """Reactive computation that tracks signals and re-runs when they change.

    Also serves as an ownership scope: child computations created during
    execution are disposed before each re-run, preventing leaks from
    conditionally-created effects.

    Attributes:
        _fn: The callback executed by `run()`.
        _deps: Set of signals this computation currently subscribes to.
            Cleared and rebuilt on every `run()`.
    """

    __slots__ = ("_fn", "_deps")

    def __init__(self, fn: Callable[[], Any]) -> None:
        super().__init__()
        self._fn = fn
        self._deps: Set[Signal[Any]] = set()

    def _track(self, signal: "Signal[Any]") -> None:
        if self._disposed:
            return
        if signal not in self._deps:
            self._deps.add(signal)
            signal._add_subscriber(self)

    def run(self) -> None:
        """Re-execute the tracked function, refreshing its dependency set.

        Disposes child owners and runs cleanups before each re-run so that
        conditional effects don't leak. The previous dependency edges are
        torn down and rebuilt while the body executes under this owner.
        """
        if self._disposed:
            return
        self._dispose_children()
        self._run_cleanups()
        for s in list(self._deps):
            s._remove_subscriber(self)
        self._deps.clear()
        global _current_owner, _current_computation
        prev_owner = _current_owner
        prev_comp = _current_computation
        _current_owner = self
        _current_computation = self
        try:
            self._fn()
        finally:
            _current_owner = prev_owner
            _current_computation = prev_comp

    def schedule(self) -> None:
        """Enqueue this computation for the next flush.

        Called by `Signal.set` when a tracked dependency changes. When no
        batch is active a microtask flush is scheduled; otherwise the
        computation is held until the outermost batch completes.
        """
        if self._disposed:
            return
        if self not in _pending_set:
            _pending_set.add(self)
            _pending_queue.append(self)
        if _batch_depth == 0:
            _schedule_flush()

    def dispose(self) -> None:
        """Dispose the computation and unsubscribe from all dependencies.

        Removes this computation from any pending flush queue, clears
        dependency edges, and tears down child owners and cleanups.
        """
        if self._disposed:
            return
        self._disposed = True
        self._dispose_children()
        for s in list(self._deps):
            s._remove_subscriber(self)
        self._deps.clear()
        _pending_set.discard(self)
        self._run_cleanups()
        if self._parent is not None:
            try:
                self._parent._children.remove(self)
            except ValueError:
                pass
            self._parent = None


# ---------------------------------------------------------------------------
# Signal
# ---------------------------------------------------------------------------


class Signal(Generic[T]):
    """Mutable reactive container that notifies subscribed computations on change.

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
        self._subscribers: List[Computation] = []
        self._subscriber_set: Set[Computation] = set()
        self._equals = equals

    def _add_subscriber(self, comp: "Computation") -> None:
        if comp not in self._subscriber_set:
            self._subscriber_set.add(comp)
            self._subscribers.append(comp)

    def _remove_subscriber(self, comp: "Computation") -> None:
        if comp in self._subscriber_set:
            self._subscriber_set.discard(comp)
            try:
                self._subscribers.remove(comp)
            except ValueError:
                pass

    def get(self) -> T:
        """Return the current value and subscribe the active computation.

        When called inside an effect, memo, or reactive hole, this signal
        is added to that computation's dependency set so it re-runs on
        future writes. Outside a tracking context the read is untracked.

        Returns:
            The current value held by the signal.
        """
        if _current_computation is not None:
            _current_computation._track(self)
        return self._value

    def set(self, value: T) -> None:
        """Write a new value and notify subscribers if it changed.

        Equality is determined by the `equals` policy passed to the
        constructor (default: `is` then `==`, with `equals=False` to
        bypass the check entirely).

        Args:
            value: The new value to store.
        """
        if self._equals is not False:
            if callable(self._equals):
                if self._equals(self._value, value):
                    return
            else:
                # Default / ``equals=True`` -- value equality with an
                # identity fast-path.  ``is`` first (cheap and short-
                # circuits for the common "same reference" case, e.g.
                # mutate-then-set with no fresh allocation), then ``==``
                # so a new container with equal contents still skips
                # notification.  This matches Python's natural intuition
                # (``data.append(x); set_data(data)`` is a no-op because
                # the value didn't change) while letting users opt into
                # identity-only semantics with
                # ``equals=lambda a, b: a is b`` or skip altogether with
                # ``equals=False``.
                if value is self._value:
                    return
                try:
                    if value == self._value:
                        return
                except Exception:
                    pass
        self._value = value
        for comp in list(self._subscribers):
            comp.schedule()


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

    Every attribute or item access returns a **reactive accessor** — a
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
            # Auto-hole — only the text node updates when ``name`` changes.
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

        If the stored prop value is a getter, it is invoked and the result
        returned — mirroring `_make_getter`. If `default` is provided, it is
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
        """Update props from parent (called by reconciler on re-render)."""
        signals = object.__getattribute__(self, "_signals")
        defaults = object.__getattribute__(self, "_defaults")
        object.__setattr__(self, "_raw", dict(new_props))
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
        signal — a tracking scope subscribes to it.

        When `key` is **missing**, the getter returns `default` on each call
        without creating a tracked signal. This means repeated `get(key, x)`
        / `get(key, y)` calls each return their own default (no sticky
        behavior). Components that need reactivity for a possibly-missing
        prop should declare it as a parameter with a default value —
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

        The result reflects the latest props pushed into the proxy (it is
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
# Prop-reading helpers (work uniformly on ReactiveProps and plain dicts)
# ---------------------------------------------------------------------------


def read_prop(props: Any, key: str, default: Any = None) -> Any:
    """Return the current value for `key` from `props`.

    Works with both [`ReactiveProps`][wybthon.ReactiveProps] (the common
    case inside the reconciler) and plain dicts (test paths and a few
    legacy call sites). When called inside a tracking scope, the read is
    tracked against the underlying signal — mirroring the auto-unwrap
    behavior of `ReactiveProps.value`.

    Args:
        props: A `ReactiveProps` proxy or any dict-like object.
        key: Prop name to read.
        default: Returned when `key` is absent. Defaults to `None`.

    Returns:
        The current value, with auto-unwrap applied for `ReactiveProps`.
    """
    if isinstance(props, ReactiveProps):
        return props.value(key, default)
    if hasattr(props, "get"):
        return props.get(key, default)
    return default


def iter_prop_keys(props: Any) -> List[str]:
    """Return the list of prop keys present on `props`.

    Same uniform shim as [`read_prop`][wybthon.reactivity.read_prop] for
    components that iterate over an unknown prop bag (e.g. `Link`
    forwarding extra attributes onto the rendered `<a>`).

    Args:
        props: A `ReactiveProps` proxy or any object with `.keys()`.

    Returns:
        A list of present keys, or an empty list when `props` is not
        dict-like.
    """
    if isinstance(props, ReactiveProps):
        return list(props)
    if hasattr(props, "keys"):
        return list(props.keys())
    return []


# ---------------------------------------------------------------------------
# Computed (memo)
# ---------------------------------------------------------------------------


class _Computed(Generic[T]):
    """Read-only signal whose value is derived from other signals.

    Backs [`create_memo`][wybthon.create_memo] and the public type
    alias `Computed`. The internal `Computation` re-runs whenever any
    of its tracked signals change, recomputing the value.
    """

    def __init__(self, fn: Callable[[], T]) -> None:
        self._value_signal: Signal[T] = Signal(cast(T, None))

        def runner() -> None:
            self._value_signal.set(fn())

        self._comp = Computation(runner)
        if _current_owner is not None:
            _current_owner._add_child(self._comp)
        self._comp.run()

    def get(self) -> T:
        return self._value_signal.get()

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
    comp = Computation(fn)
    if _current_owner is not None:
        _current_owner._add_child(comp)
    comp.run()
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
    computations exactly once when the outermost batch exits.
    """

    def __enter__(self) -> None:
        global _batch_depth
        _batch_depth += 1

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        global _batch_depth
        _batch_depth -= 1
        if _batch_depth == 0 and _pending_set:
            _flush()


def batch(fn: Optional[Callable[[], T]] = None) -> Union[T, _Batch]:
    """Batch signal updates so subscribers flush once at the end.

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
    Effects are flushed synchronously before `batch` returns, matching
    SolidJS semantics.

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
        if _batch_depth == 0 and _pending_set:
            _flush()
    return result


def untrack(fn: Callable[[], T]) -> T:
    """Run `fn` without tracking any signal reads.

    Useful inside effects when you need to read a signal without creating
    a dependency, or during component setup to seed local state from a
    prop without subscribing.

    Inside `untrack` the dev-mode destructured-prop warning is also
    silenced — so `count, set_count = create_signal(untrack(initial))`
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
    global _current_computation, _untrack_depth
    prev = _current_computation
    _current_computation = None
    _untrack_depth += 1
    try:
        return fn()
    finally:
        _untrack_depth -= 1
        _current_computation = prev


# ---------------------------------------------------------------------------
# Async resource
# ---------------------------------------------------------------------------

R = TypeVar("R")

FetchFn = Callable[..., Union[Awaitable[R], R]]


class Resource(Generic[R]):
    """Async resource with reactive `data`, `error`, and `loading` signals.

    Wraps an awaitable fetcher and exposes signal-backed state so consumers
    can render loading and error UIs declaratively (typically with
    [`Suspense`][wybthon.Suspense]).

    Use `reload()` to (re)fetch and `cancel()` to abort the in-flight
    request.

    When constructed with a `source` getter, the resource automatically
    refetches when the source's tracked value changes (skipping the very
    first read so it doesn't double-fetch on creation).

    Attributes:
        data: Reactive accessor for the most recent successful payload, or
            `None` before any fetch completes.
        error: Reactive accessor for the most recent exception, or `None`.
        loading: Reactive accessor; `True` while a fetch is in flight.

    Example:
        ```python
        async def load_user(signal=None):
            resp = await fetch("/api/users/1")
            return await resp.json()

        user = create_resource(load_user)
        h("p", {}, dynamic(lambda: "Loading..." if user.loading() else user.data().get("name")))
        ```
    """

    def __init__(self, fetcher: FetchFn, source: Optional[Callable[[], Any]] = None) -> None:
        import asyncio
        import inspect

        self._asyncio = asyncio
        self._inspect = inspect
        self._fetcher: FetchFn = fetcher
        self._source = source
        self._task: Optional[asyncio.Task[Any]] = None
        self._abort_controller: Any = None
        self._version: int = 0

        self.data: Signal[Optional[R]] = Signal(None)
        self.error: Signal[Optional[Any]] = Signal(None)
        self.loading: Signal[bool] = Signal(False)

        self.reload()

        if source is not None:
            self._source_effect: Optional[Computation] = None
            self._setup_source_tracking()

    def _setup_source_tracking(self) -> None:
        """Watch the `source` getter and call `reload()` whenever it changes."""
        first_run = [True]

        def watcher() -> None:
            assert self._source is not None
            self._source()
            if first_run[0]:
                first_run[0] = False
                return
            self.reload()

        self._source_effect = effect(watcher)

    def _make_abort_controller(self) -> Any:
        try:
            from js import AbortController

            return AbortController.new()
        except Exception:
            return None

    async def _run(self, current_version: int, controller: Any) -> None:
        try:
            if self._inspect.signature(self._fetcher).parameters.get("signal") is not None:
                coro_or_val = self._fetcher(signal=getattr(controller, "signal", None))
            else:
                coro_or_val = self._fetcher()

            if isinstance(coro_or_val, AbcAwaitable):
                result = await coro_or_val
            else:
                result = cast(R, coro_or_val)

            if current_version == self._version:
                self.error.set(None)
                self.data.set(result)
                self.loading.set(False)
        except Exception as e:
            if current_version != self._version:
                return
            self.error.set(e)
            self.loading.set(False)

    def reload(self) -> None:
        """Cancel any in-flight request and start a new fetch.

        Bumps the internal version, sets `loading` to `True`, clears
        `error`, and dispatches the fetcher on the asyncio loop. Older
        in-flight tasks are ignored when they resolve.
        """
        self.cancel()
        self._version += 1
        self.loading.set(True)
        self.error.set(None)

        controller = self._make_abort_controller()
        self._abort_controller = controller

        async def runner() -> None:
            await self._run(self._version, controller)

        try:
            self._task = self._asyncio.create_task(runner())
        except Exception:
            self._asyncio.get_event_loop().create_task(runner())

    def cancel(self) -> None:
        """Abort the current in-flight fetch, if any.

        Calls `AbortController.abort()` on the wrapped browser controller,
        cancels the asyncio task, and resets `loading` to `False` without
        touching `data` or `error`.
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
            self.loading.set(False)
        except Exception:
            pass


def create_resource(
    source_or_fetcher: Union[Callable[[], Any], Callable[..., Awaitable[R]]],
    fetcher: Optional[Callable[..., Awaitable[R]]] = None,
) -> Resource[R]:
    """Create an async [`Resource`][wybthon.Resource] with cancellation support.

    Can be called two ways:

    - `create_resource(fetcher)` — simple fetcher, no source signal.
    - `create_resource(source, fetcher)` — refetches automatically when the
      `source` getter's tracked value changes.

    The fetcher should be an async function returning the data value. If it
    accepts a `signal` keyword argument, an `AbortSignal` is passed for
    cancellation support when running in a browser.

    Args:
        source_or_fetcher: When called with one argument, this is the
            fetcher. When called with two, this is the source getter
            (typically a signal accessor).
        fetcher: Optional fetcher. Required when `source_or_fetcher` is a
            source getter.

    Returns:
        A `Resource[R]` whose `data`, `error`, and `loading` signals can
        be read inside reactive scopes.

    Example:
        ```python
        user_id, set_user_id = create_signal(1)

        async def load_user(signal=None):
            resp = await fetch(f"/api/users/{user_id()}")
            return await resp.json()

        user = create_resource(user_id, load_user)
        ```
    """
    if fetcher is None:
        return Resource(source_or_fetcher)
    return Resource(fetcher, source=source_or_fetcher)


use_resource = create_resource


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
        "_error_handler",
        "_provider_value_signals",
    )

    def __init__(self) -> None:
        super().__init__()
        self._mount_callbacks: List[Callable[[], Any]] = []
        self._props: dict = {}
        self._reactive_props: Optional[ReactiveProps] = None
        self._vnode: Any = None
        self._error_handler: Optional[Callable[..., Any]] = None
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

    Capture the owner before crossing async boundaries (e.g. `await`) and
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
    naturally — there is no cursor system or "rules of hooks".

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
        suitable for embedding as a reactive hole.

    Example:
        ```python
        count, set_count = create_signal(0)
        print(count())          # 0
        set_count(5)
        print(count())          # 5
        ```
    """
    sig: Signal[Any] = Signal(value, equals=equals)
    return sig.get, sig.set


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
    import inspect as _inspect

    try:
        _sig = _inspect.signature(fn)
        _positional = [
            p
            for p in _sig.parameters.values()
            if p.kind in (_inspect.Parameter.POSITIONAL_ONLY, _inspect.Parameter.POSITIONAL_OR_KEYWORD)
            and p.default is _inspect.Parameter.empty
        ]
        _accepts_prev = len(_positional) > 0
    except (ValueError, TypeError):
        _accepts_prev = False

    _prev: List[Any] = [None]

    def wrapped() -> None:
        if _accepts_prev:
            _prev[0] = fn(_prev[0])
        else:
            fn()

    comp = Computation(wrapped)
    if _current_owner is not None:
        _current_owner._add_child(comp)
    comp.run()
    return comp


def create_memo(fn: Callable[[], T]) -> Callable[[], T]:
    """Create an auto-tracking computed value and return its getter.

    Re-computes only when signals read inside `fn` change. Inside a
    component, the underlying computation is disposed on unmount.

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

    Wraps a getter that returns children (e.g. `lambda: props.children()`)
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
    by `@component`. Use `get_props()` for advanced cases — generic
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

        global _current_computation
        prev = _current_computation
        _current_computation = None
        try:
            call_fn()
        finally:
            _current_computation = prev

    return create_effect(tracked)


def create_root(fn: Callable[[Callable[[], None]], T]) -> T:
    """Run `fn` inside an independent reactive root.

    Useful for spawning long-lived reactive work that should not be tied
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
    """Call `src` if it is a callable getter; otherwise return as-is."""
    if src is None:
        return None
    if callable(src) and not isinstance(src, dict):
        return src()
    return src


class _MergedProps:
    """Reactive merged-props proxy returned by [`merge_props`][wybthon.merge_props].

    Reading a key lazily checks sources right-to-left. When a source is a
    callable (e.g. a signal getter returning a dict), it is called on each
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
    iteration). When a source is a callable, it is called on each property
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
        global _map_key_counter, _current_owner, _current_computation
        items = source()
        if not items:
            for entry in _cache:
                entry["owner"].dispose()
            _cache.clear()
            return []

        new_cache: List[Dict[str, Any]] = []
        used = [False] * len(_cache)

        for idx, item in enumerate(items):
            found = -1
            for ci in range(len(_cache)):
                if not used[ci] and item is _cache[ci]["item"]:
                    found = ci
                    break

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

                prev_owner = _current_owner
                prev_comp = _current_computation
                _current_owner = owner
                _current_computation = None
                try:
                    result = map_fn(item_sig.get, idx_sig.get)
                finally:
                    _current_owner = prev_owner
                    _current_computation = prev_comp

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
        global _current_owner, _current_computation
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

                prev_owner = _current_owner
                prev_comp = _current_computation
                _current_owner = owner
                _current_computation = None
                try:
                    result = map_fn(item_sig.get, i)
                finally:
                    _current_owner = prev_owner
                    _current_computation = prev_comp

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
    notified — instead of every subscriber re-running.

    Args:
        source: Zero-arg getter returning the currently-selected key.

    Returns:
        A function `is_selected(key) -> bool` that is reactive to
        selection changes.

    Example:
        ```python
        selected, set_selected = create_signal(1)
        is_selected = create_selector(selected)

        # Inside a For loop per item:
        create_effect(lambda: print("active:", is_selected(item_id)))
        ```
    """
    _subs: Dict[Any, List["Computation"]] = {}
    _prev_key: List[Any] = [None]
    _first = [True]

    def _tracker() -> None:
        new_key = source()
        old_key = _prev_key[0]
        _prev_key[0] = new_key

        if _first[0]:
            _first[0] = False
            return

        if old_key == new_key:
            return

        for comp in list(_subs.get(old_key, [])):
            comp.schedule()
        for comp in list(_subs.get(new_key, [])):
            comp.schedule()

    _effect = Computation(_tracker)
    if _current_owner is not None:
        _current_owner._add_child(_effect)
    _effect.run()

    def is_selected(key: Any) -> bool:
        if _current_computation is not None:
            subs = _subs.setdefault(key, [])
            comp = _current_computation
            if comp not in subs:
                subs.append(comp)
        return _prev_key[0] == key

    return is_selected
