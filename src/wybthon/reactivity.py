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
    "Signal",
    "Computation",
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
    "merge_props",
    "split_props",
]

T = TypeVar("T")

# ---------------------------------------------------------------------------
# Global reactive state
# ---------------------------------------------------------------------------

_current_owner: Optional["Owner"] = None
_current_computation: Optional["Computation"] = None

_pending_queue: Deque["Computation"] = deque()
_pending_set: Set["Computation"] = set()
_flush_scheduled: bool = False
_batch_depth: int = 0


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

    def __init__(self, value: T) -> None:
        self._value: T = value
        self._subscribers: List[Computation] = []
        self._subscriber_set: Set[Computation] = set()

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
        if value == self._value:
            return
        self._value = value
        for comp in list(self._subscribers):
            comp.schedule()


def signal(value: T) -> Signal[T]:
    """Create a new ``Signal`` with the given initial value."""
    return Signal(value)


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
    """
    global _current_computation
    prev = _current_computation
    _current_computation = None
    try:
        return fn()
    finally:
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

    Tracks lifecycle callbacks, the optional render function, and
    reactive props signals for stateful components.  Extends ``Owner``
    so that effects created during setup are automatically disposed
    when the component unmounts.
    """

    __slots__ = (
        "_mount_callbacks",
        "_render_fn",
        "_props",
        "_props_signal",
        "_prop_signals",
        "_vnode",
        "_error_handler",
    )

    def __init__(self) -> None:
        super().__init__()
        self._mount_callbacks: List[Callable[[], Any]] = []
        self._render_fn: Optional[Callable[[], Any]] = None
        self._props: dict = {}
        self._props_signal: Optional[Signal[Any]] = None
        self._prop_signals: Dict[str, Signal[Any]] = {}
        self._vnode: Any = None
        self._error_handler: Optional[Callable[..., Any]] = None

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


# ---------------------------------------------------------------------------
# Public primitives
# ---------------------------------------------------------------------------


def create_signal(value: T) -> tuple:
    """Create a reactive signal.  Returns ``(getter, setter)``.

    Works inside or outside components.  Inside a stateful component the
    signal is captured by the render function's closure and persists
    naturally (no cursor system needed).

    Example::

        count, set_count = create_signal(0)
        print(count())          # 0
        set_count(5)
        print(count())          # 5
    """
    sig: Signal[Any] = Signal(value)
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


def get_props() -> Callable[[], dict]:
    """Return a reactive getter for the current component's props.

    Useful in stateful components that need to react to parent prop changes::

        props = get_props()
        create_effect(lambda: print("query changed:", props()["query"]))
    """
    ctx = _get_component_ctx()
    if ctx is None:
        raise RuntimeError("get_props() can only be called inside a component")
    if ctx._props_signal is None:
        ctx._props_signal = Signal(ctx._props)
    return ctx._props_signal.get


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


def merge_props(*sources: dict) -> dict:
    """Merge multiple prop dicts.  Later sources win on conflict.

    Example::

        defaults = {"size": "md", "variant": "solid"}
        final = merge_props(defaults, props)
    """
    out: dict = {}
    for src in sources:
        if src:
            out.update(src)
    return out


def split_props(
    props: dict,
    *key_groups: List[str],
) -> Tuple[dict, ...]:
    """Split a props dict into groups by key name, plus a rest dict.

    Returns ``(group1, group2, ..., rest)`` where *rest* contains keys
    not claimed by any group.

    Example::

        local, rest = split_props(props, ["class", "style"])
    """
    results: List[dict] = []
    used: set = set()
    for group in key_groups:
        d: dict = {}
        for key in group:
            if key in props:
                d[key] = props[key]
                used.add(key)
        results.append(d)
    rest = {k: v for k, v in props.items() if k not in used}
    results.append(rest)
    return tuple(results)
