"""Signal-based reactive primitives with ownership tree, inspired by SolidJS.

The ownership tree ensures that every reactive computation (effect, memo)
is **owned** by its parent scope.  When a parent re-runs or is disposed,
all child computations are automatically cleaned up -- preventing memory
leaks and ensuring correct lifecycle semantics.

Key classes:

- ``Owner``        -- base ownership scope (cleanups + child tracking)
- ``Computation``  -- reactive computation that is also an ownership scope
- ``Signal``       -- mutable reactive container

Key functions:

- ``create_signal``  -- create a (getter, setter) pair
- ``create_effect``  -- auto-tracking side-effect
- ``create_memo``    -- auto-tracking derived value
- ``on_mount``       -- run once after component mount
- ``on_cleanup``     -- register teardown callback
- ``create_root``    -- create an independent reactive root
- ``batch``          -- batch signal updates
- ``untrack``        -- read without tracking
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
    """Return True when the current call stack is inside :func:`untrack`."""
    return _untrack_depth > 0


def _has_current_computation() -> bool:
    """Return True when there is an active reactive computation (effect/memo).

    Used by the dev-mode "destructured prop" warning to suppress noise
    when a prop accessor is read inside an effect / memo body during
    setup -- those are the canonical "subscribe to this prop" patterns,
    not the footgun the warning is trying to flag.
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

    Tracks child owners and cleanup callbacks.  When disposed, children
    are disposed first (depth-first), then own cleanups run.  This
    mirrors SolidJS's ownership model.
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
    """Reactive computation that tracks Signals and re-runs when they change.

    Also serves as an ownership scope: child computations created during
    execution are disposed before each re-run, preventing leaks from
    conditionally-created effects.
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
        if self._disposed:
            return
        if self not in _pending_set:
            _pending_set.add(self)
            _pending_queue.append(self)
        if _batch_depth == 0:
            _schedule_flush()

    def dispose(self) -> None:
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
    """Mutable container that notifies subscribed computations on changes."""

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
        if _current_computation is not None:
            _current_computation._track(self)
        return self._value

    def set(self, value: T) -> None:
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
    """Create a new ``Signal`` with the given initial value."""
    return Signal(value)


# ---------------------------------------------------------------------------
# ReactiveProps
# ---------------------------------------------------------------------------


class ReactiveProps:
    """Reactive proxy for component props.

    Every prop access returns a **reactive accessor** (a zero-argument
    callable that returns the current value and tracks the read).
    This matches SolidJS's ``props.x`` semantics adapted to Python::

        props.name        # → callable getter
        props.name()      # → current value (tracked)
        props["name"]     # → callable getter (same as ``props.name``)
        props.get("name", default)  # → callable getter, returns default if missing

    Pass a getter directly into a VNode tree to create an automatic
    reactive hole — the surrounding DOM region updates when the prop
    changes::

        return p("Hello, ", props.name, "!")  # auto-hole on props.name

    To unwrap once at setup time (untracked initial value)::

        initial = props.name()    # current value, no tracking inside body

    To iterate / introspect the props dict::

        for key in props:           # keys
            print(key, props.value(key))    # ``value()`` returns the current value
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
        """Return a stable, callable accessor for *key* (cached).

        The accessor reads the prop signal and, when the stored value is
        itself a getter (callable with no required args), transparently
        calls it.  This means parents can pass either a static value
        (``count=5``) or a getter (``count=count_signal.get`` /
        ``count=lambda: total()``) and children always read the current
        value the same way: ``props.count()``.  Reactivity is tracked
        through *both* the prop signal and any underlying source.
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
        """Return the current value for *key* (tracked, with auto-unwrap).

        If the stored prop value is a getter, it is invoked and the
        result returned -- mirroring :meth:`_make_getter`.  If *default*
        is provided, it is returned when *key* is absent from both the
        props dict and the component's parameter defaults.
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
        """Return a callable getter for *key*, falling back to *default* when missing.

        When *key* exists on the prop bag (in raw props, prior signals,
        or component-parameter defaults), the returned getter reads the
        underlying signal -- a tracking scope subscribes to it.

        When *key* is **missing**, the getter returns *default* on each
        call without creating a tracked signal.  This means repeated
        ``get(key, x)`` / ``get(key, y)`` calls each return their own
        default (no sticky behavior).  Components that need reactivity
        for a possibly-missing prop should declare it as a parameter
        with a default value -- ``@component`` ensures a signal is
        created up front so future updates always propagate.
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
        raw = object.__getattribute__(self, "_raw")
        return raw.keys()

    def values(self) -> Any:
        """Return current prop values as a list (tracked)."""
        raw = object.__getattribute__(self, "_raw")
        return [self._signal_for(k).get() for k in raw]

    def items(self) -> Any:
        """Return ``(key, current_value)`` pairs (tracked)."""
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
    """Return the current value for *key* from *props*.

    Works with both :class:`ReactiveProps` (the common case inside the
    reconciler) and plain dicts (test paths and a few legacy code
    sites).  When called inside a tracking scope, the read is tracked
    against the underlying signal -- mirroring the auto-unwrap behavior
    of :meth:`ReactiveProps.value`.
    """
    if isinstance(props, ReactiveProps):
        return props.value(key, default)
    if hasattr(props, "get"):
        return props.get(key, default)
    return default


def iter_prop_keys(props: Any) -> List[str]:
    """Return the list of prop keys present on *props*.

    Same uniform shim as :func:`read_prop` for components that need to
    iterate over an unknown prop bag (e.g. ``Link`` forwarding extra
    attributes onto the rendered ``<a>``).
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
    """Read-only signal computed from other signals."""

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


# Public alias for the computed-value type.  Users who want to type-hint a
# memoised value (for example, ``Computed[int]``) should reach for this name.
# The constructor lives at :func:`create_memo` (returns a getter, not the
# class instance), but the type itself is part of the public surface.
Computed = _Computed


def computed(fn: Callable[[], T]) -> _Computed[T]:
    """Create a computed value that derives from other signals."""
    return _Computed(fn)


def effect(fn: Callable[[], Any]) -> Computation:
    """Run a reactive effect and return its computation handle."""
    comp = Computation(fn)
    if _current_owner is not None:
        _current_owner._add_child(comp)
    comp.run()
    return comp


def on_effect_cleanup(comp: Computation, fn: Callable[[], Any]) -> None:
    """Register a cleanup callback to run when a computation is disposed."""
    comp._cleanups.append(fn)


# ---------------------------------------------------------------------------
# Batch
# ---------------------------------------------------------------------------


class _Batch:
    """Context manager to batch signal updates into a single flush."""

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

    Can be used as a **context manager** (Pythonic style)::

        with batch():
            set_a(1)
            set_b(2)

    Or with a **callback** (SolidJS style)::

        batch(lambda: (set_a(1), set_b(2)))

    When called with a function, the function's return value is returned.
    Effects are flushed synchronously before ``batch`` returns, matching
    SolidJS semantics.
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
    """Run *fn* without tracking any signal reads.

    Useful inside effects when you need to read a signal without creating
    a dependency::

        create_effect(lambda: print("a changed:", a(), "b is:", untrack(b)))

    Inside ``untrack`` the dev-mode destructured-prop warning is also
    silenced -- so ``count, set_count = create_signal(untrack(initial))``
    cleanly opts out of the noise.
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
    """Async resource wrapper with Signals for data, error, and loading.

    Use `reload()` to (re)fetch, `cancel()` to cancel the in-flight request.
    Optionally accepts a *source* getter; when the source signal changes the
    resource automatically refetches.
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
        """Watch the source signal and refetch when it changes."""
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
    """Create an async Resource with loading/error states and cancellation.

    Can be called two ways:

    - ``create_resource(fetcher)`` -- simple fetcher, no source signal.
    - ``create_resource(source, fetcher)`` -- refetches automatically when
      the *source* getter's return value changes.

    The *fetcher* should be an async function returning the data value.
    If it accepts a ``signal`` keyword argument, an AbortSignal will be
    passed for cancellation support when available.
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

    Tracks lifecycle callbacks and reactive prop signals for stateful
    components.  Extends ``Owner`` so that effects created during
    setup are automatically disposed when the component unmounts.
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
    """Return the current reactive owner, if any."""
    return _current_owner


def _get_component_ctx() -> Optional[_ComponentContext]:
    """Walk up the ownership chain to find the nearest component context."""
    owner = _current_owner
    while owner is not None:
        if isinstance(owner, _ComponentContext):
            return owner
        owner = owner._parent
    return None


def get_owner() -> Optional[Owner]:
    """Return the current reactive owner scope, if any.

    Capture the owner before crossing async boundaries (e.g. ``await``)
    and restore it with ``run_with_owner`` to maintain proper lifecycle
    management.
    """
    return _current_owner


def run_with_owner(owner: Optional[Owner], fn: Callable[[], T]) -> T:
    """Run *fn* under the given ownership scope.

    Useful for restoring context after an ``await`` boundary where
    the reactive owner would otherwise be lost::

        owner = get_owner()
        data = await fetch(...)
        run_with_owner(owner, lambda: create_effect(lambda: ...))
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
    """Create a reactive signal.  Returns ``(getter, setter)``.

    Works inside or outside components.  Inside a stateful component the
    signal is captured by the render function's closure and persists
    naturally (no cursor system needed).

    The *equals* parameter controls when subscribers are notified:

    - default (or ``True``) — **value equality** (``new == old``) with
      an identity fast-path.  Skips notification when the new value is
      ``is``-identical *or* ``==``-equal to the old.  This matches
      Python's natural intuition: re-setting an unchanged value is a
      no-op, but a fresh container with equal contents *also* skips
      (so ``data.append(x); set_data(data)`` does **not** notify —
      copy the container or use ``equals=False`` if you need that).
    - ``False`` — always notify on every ``set()`` call, even when the
      new value is identical or equal to the old.  Useful for "fire
      a change event" signals.
    - A callable ``(old, new) -> bool`` — skip notification when it
      returns ``True``.  Pass ``equals=lambda a, b: a is b`` for
      SolidJS-style identity-only semantics.

    Example::

        count, set_count = create_signal(0)
        print(count())          # 0
        set_count(5)
        print(count())          # 5
    """
    sig: Signal[Any] = Signal(value, equals=equals)
    return sig.get, sig.set


def create_effect(fn: Callable[..., Any]) -> Computation:
    """Create an auto-tracking reactive effect.

    The effect runs immediately and re-runs whenever any signal read
    inside *fn* changes.  ``on_cleanup`` may be called inside *fn* to
    register per-run cleanup (runs before re-execution and on disposal).

    If *fn* accepts a positional parameter, the **previous return value**
    is passed on each re-execution (``None`` on the first run), matching
    SolidJS ``createEffect(prev => ...)``::

        create_effect(lambda prev: (print("was", prev), count())[1])

    Inside a component, the effect is automatically disposed on unmount.
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
    """Create an auto-tracking computed value.  Returns a *getter* function.

    Re-computes only when signals read inside *fn* change.  Inside a
    component, the underlying computation is disposed on unmount.

    Example::

        doubled = create_memo(lambda: count() * 2)
        print(doubled())  # reactive read
    """
    c = _Computed(fn)
    return c.get


def on_mount(fn: Callable[[], Any]) -> None:
    """Register a callback to run once after the component mounts.

    Must be called during a component's setup phase (the body of a
    ``@component`` function, before the ``return``).
    """
    ctx = _get_component_ctx()
    if ctx is None:
        raise RuntimeError("on_mount() can only be called inside a component's setup phase")
    ctx._mount_callbacks.append(fn)


def on_cleanup(fn: Callable[[], Any]) -> None:
    """Register a cleanup callback.

    - Inside ``create_effect``: runs before each re-execution and on disposal.
    - Inside a component's setup phase: runs when the component unmounts.
    """
    if _current_owner is not None:
        _current_owner._cleanups.append(fn)
    else:
        raise RuntimeError("on_cleanup() must be called inside a component or create_effect()")


def children(fn: Callable[[], Any]) -> Callable[[], List[Any]]:
    """Resolve and memoize reactive children.

    Wraps a getter that returns children (e.g. ``lambda: props.children``)
    and returns a memo that flattens and resolves the children list.
    Matches SolidJS ``children()`` helper.
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
    """Return the reactive props proxy for the current component.

    The returned ``ReactiveProps`` object provides reactive access
    to individual props.  Each attribute / index lookup yields a
    callable getter; call the getter to read the current value
    (tracked).  Use ``get_props()`` for advanced cases — most
    components should rely on the destructured parameters provided
    by ``@component``::

        @component
        def Greet(name="world"):
            # ``name`` is a reactive accessor.
            return p("Hello, ", name, "!")

        @component
        def Advanced():
            props = get_props()
            create_effect(lambda: print("name:", props.name()))
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

    *deps* is a single getter or a list of getters.  *fn* receives the
    current value(s) as positional arguments.  Only the listed deps are
    tracked; the body of *fn* is run inside ``untrack``.

    When *defer* is ``True`` the effect skips the first execution
    (useful for reacting only to changes, not the initial value).

    Example::

        on(count, lambda v: print("count is now", v))
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
    """Run *fn* with an independent reactive root.

    *fn* receives a ``dispose`` callback that tears down all effects
    created inside the root::

        result = create_root(lambda dispose: ...)
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
    """Call *src* if it is a callable getter; otherwise return as-is."""
    if src is None:
        return None
    if callable(src) and not isinstance(src, dict):
        return src()
    return src


class _MergedProps:
    """Reactive merged-props proxy.

    Reading a key lazily checks sources right-to-left.  When a source
    is a callable (e.g. a signal getter returning a dict), it is called
    on each access, so reads inside reactive computations are tracked
    automatically.
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
    """Reactive split-props proxy that filters keys from a source.

    Reads are forwarded to the underlying source, so callable sources
    maintain reactive tracking.
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

    Each source may be a plain ``dict``, a zero-arg getter that returns
    a dict, or another ``_MergedProps`` / ``_SplitProps``.  Later sources
    override earlier ones on key conflicts.

    The returned object supports dict-like access (``[]``, ``.get``,
    ``in``, iteration).  When a source is a callable, it is called on
    each property access, so signal reads inside the getter are tracked
    by the current reactive computation.

    Example::

        defaults = {"size": "md", "variant": "solid"}
        final = merge_props(defaults, props)
        # final["size"] lazily reads from props, then defaults
    """
    return _MergedProps(list(sources))


def split_props(
    props: Any,
    *key_groups: List[str],
) -> Tuple[Any, ...]:
    """Split a props source into groups by key name, plus a rest group.

    Returns ``(group1, group2, ..., rest)`` where each group is a
    reactive proxy that lazily reads from the original *props*.

    *props* may be a plain ``dict``, a callable getter, or a
    ``_MergedProps`` / ``_SplitProps``.

    Example::

        local, rest = split_props(props, ["class", "style"])
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
    """Keyed reactive list mapping with stable per-item scopes.

    *source* is a zero-arg getter returning a list (typically a signal
    accessor).  *map_fn* receives ``(item_getter, index_getter)`` and is
    called **once** per unique item (matched by reference identity).
    When an item leaves the list its reactive scope is disposed.

    Returns a getter that produces the mapped list.  Reading it inside
    a reactive computation creates a dependency — the getter updates
    whenever the source list changes.

    Example::

        items, set_items = create_signal(["A", "B", "C"])
        mapped = map_array(items, lambda item, idx: f"{idx()}: {item()}")
        create_effect(lambda: print(mapped()))  # ["0: A", "1: B", "2: C"]
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
    """Index-keyed reactive list mapping with stable per-index scopes.

    Unlike :func:`map_array`, scopes are keyed by *index position*.
    Each slot has a reactive ``item_getter`` signal that updates when
    the value at that index changes.  *map_fn* receives
    ``(item_getter, index: int)`` — the index is a plain ``int``, not
    a getter.

    Returns a getter producing the mapped list.

    Example::

        items, set_items = create_signal(["A", "B", "C"])
        mapped = index_array(items, lambda item, idx: f"[{idx}] {item()}")
        create_effect(lambda: print(mapped()))
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
    """Create an efficient selection signal.

    Returns ``is_selected(key) -> bool``.  When the source value
    changes, only computations that called ``is_selected`` with the
    **previous** or **new** key are notified — giving O(1) updates
    instead of O(n).

    Example::

        selected, set_selected = create_signal(1)
        is_selected = create_selector(selected)

        # Inside a For loop per item:
        create_effect(lambda: print("active:", is_selected(item_id)))
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
