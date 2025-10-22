"""Signal-based reactive primitives and async Resource helper."""

from __future__ import annotations

from collections import deque
from collections.abc import Awaitable as AbcAwaitable
from typing import Any, Awaitable, Callable, Deque, Generic, List, Optional, Set, TypeVar, Union, cast

__all__ = [
    "Signal",
    "Computation",
    "signal",
    "computed",
    "effect",
    "on_effect_cleanup",
    "batch",
    "Resource",
    "use_resource",
]

T = TypeVar("T")


_current_computation: Optional["Computation"] = None
# Deterministic FIFO pending queue and membership set
_pending_queue: Deque["Computation"] = deque()
_pending_set: Set["Computation"] = set()
_flush_scheduled: bool = False
_batch_depth: int = 0


def _schedule_flush() -> None:
    global _flush_scheduled
    if _flush_scheduled:
        return
    _flush_scheduled = True

    # Try microtask scheduling; fall back to setTimeout(0)
    try:
        from js import queueMicrotask
        from pyodide.ffi import create_once_callable

        queueMicrotask(create_once_callable(lambda: _flush()))
    except Exception:  # pragma: no cover
        # Try Pyodide setTimeout, else Python threading/asyncio fallback
        try:
            from js import setTimeout
            from pyodide.ffi import create_once_callable

            setTimeout(create_once_callable(lambda: _flush()), 0)
        except Exception:
            # Pure-Python fallback for non-browser environments
            try:
                import threading

                threading.Timer(0, _flush).start()
            except Exception:
                # Last resort: run synchronously (can re-entrantly flush)
                _flush()


def _flush() -> None:
    global _flush_scheduled
    _flush_scheduled = False
    # Process only the items that were queued at the time the flush was scheduled.
    # Any computations scheduled during this flush will run in the next microtask.
    initial_count = len(_pending_queue)
    for _ in range(initial_count):
        comp = _pending_queue.popleft()
        if comp not in _pending_set:
            # Was removed or already processed
            continue
        _pending_set.discard(comp)
        if not getattr(comp, "_is_disposed", False):
            comp.run()


class Computation:
    """Reactive computation that tracks Signals and re-runs when they change."""

    def __init__(self, fn: Callable[[], Any]) -> None:
        self._fn = fn
        self._deps: Set[Signal[Any]] = set()
        self._is_disposed = False
        self._on_dispose: List[Callable[[], Any]] = []

    def _track(self, signal: "Signal[Any]") -> None:
        if self._is_disposed:
            return
        if signal not in self._deps:
            self._deps.add(signal)
            signal._add_subscriber(self)

    def run(self) -> None:
        if self._is_disposed:
            return
        # Clear old subscriptions
        for s in list(self._deps):
            s._remove_subscriber(self)
        self._deps.clear()
        global _current_computation
        prev = _current_computation
        _current_computation = self
        try:
            self._fn()
        finally:
            _current_computation = prev

    def schedule(self) -> None:
        if self._is_disposed:
            return
        if self not in _pending_set:
            _pending_set.add(self)
            _pending_queue.append(self)
        if _batch_depth == 0:
            _schedule_flush()

    def dispose(self) -> None:
        if self._is_disposed:
            return
        self._is_disposed = True
        for s in list(self._deps):
            s._remove_subscriber(self)
        self._deps.clear()
        # Remove from pending queue membership; the actual deque node will be skipped on flush
        if self in _pending_set:
            _pending_set.discard(self)
        while self._on_dispose:
            fn = self._on_dispose.pop()
            try:
                fn()
            except Exception:
                pass


class Signal(Generic[T]):
    """Mutable container that notifies subscribed computations on changes."""

    def __init__(self, value: T) -> None:
        self._value: T = value
        # Maintain deterministic subscription order
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
        # Notify subscribers
        for comp in list(self._subscribers):
            comp.schedule()


def signal(value: T) -> Signal[T]:
    """Create a new `Signal` with the given initial value."""
    return Signal(value)


class _Computed(Generic[T]):
    """Read-only signal computed from other signals."""

    def __init__(self, fn: Callable[[], T]) -> None:
        # Initialize with a dummy value; immediately computed below
        self._value_signal: Signal[T] = Signal(cast(T, None))

        def runner() -> None:
            self._value_signal.set(fn())

        self._comp = Computation(runner)
        # Compute immediately
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
    comp.run()
    return comp


def on_effect_cleanup(comp: Computation, fn: Callable[[], Any]) -> None:
    """Register a cleanup callback to run when a computation is disposed."""
    comp._on_dispose.append(fn)


class _Batch:
    """Context manager to batch signal updates into a single flush."""

    def __enter__(self) -> None:
        global _batch_depth
        _batch_depth += 1

    def __exit__(self, exc_type, exc, tb) -> None:
        global _batch_depth
        _batch_depth -= 1
        if _batch_depth == 0 and _pending_set:
            _schedule_flush()


def batch() -> _Batch:
    """Batch signal updates within the returned context manager."""
    return _Batch()


# -------------------- Async resource utility --------------------
R = TypeVar("R")


FetchFn = Callable[..., Union[Awaitable[R], R]]


class Resource(Generic[R]):
    """Async resource wrapper with Signals for data, error, and loading.

    Use `reload()` to (re)fetch, `cancel()` to cancel the in-flight request.
    """

    def __init__(self, fetcher: FetchFn) -> None:
        # Lazily import to avoid import cycles at module import time
        import asyncio  # local import for Pyodide compatibility
        import inspect

        self._asyncio = asyncio
        self._inspect = inspect
        self._fetcher: FetchFn = fetcher
        self._task: Optional[asyncio.Task[Any]] = None
        self._abort_controller: Any = None
        self._version: int = 0

        self.data: Signal[Optional[R]] = Signal(None)
        self.error: Signal[Optional[Any]] = Signal(None)
        self.loading: Signal[bool] = Signal(False)

        # Kick off initial load
        self.reload()

    def _make_abort_controller(self) -> Any:
        try:
            from js import AbortController

            # In Pyodide, construct with .new()
            return AbortController.new()
        except Exception:
            return None

    async def _run(self, current_version: int, controller: Any) -> None:
        try:
            # If fetcher accepts a 'signal' kwarg, pass it; otherwise call without
            if self._inspect.signature(self._fetcher).parameters.get("signal") is not None:
                coro_or_val = self._fetcher(signal=getattr(controller, "signal", None))
            else:
                coro_or_val = self._fetcher()

            # Await the result if needed (support both awaitable and plain values)
            if isinstance(coro_or_val, AbcAwaitable):
                result = await coro_or_val
            else:
                result = cast(R, coro_or_val)

            # Only commit if still latest
            if current_version == self._version:
                self.error.set(None)
                self.data.set(result)
                self.loading.set(False)
        except Exception as e:
            # Ignore results if outdated
            if current_version != self._version:
                return
            self.error.set(e)
            self.loading.set(False)

    def reload(self) -> None:
        # Cancel any existing task and start a new one
        self.cancel()
        self._version += 1
        self.loading.set(True)
        # Keep last good data; reset error on new attempt
        self.error.set(None)

        controller = self._make_abort_controller()
        self._abort_controller = controller

        async def runner() -> None:
            await self._run(self._version, controller)

        try:
            self._task = self._asyncio.create_task(runner())
        except Exception:
            # As a fallback, run synchronously (Pyodide will still interleave)
            # This should rarely happen but keeps API usable.
            self._asyncio.get_event_loop().create_task(runner())

    def cancel(self) -> None:
        # Invalidate current version so any late results are ignored
        self._version += 1
        # Abort JS fetch if possible
        try:
            if self._abort_controller is not None:
                self._abort_controller.abort()
        except Exception:
            pass
        self._abort_controller = None
        # Cancel Python task if any
        try:
            if self._task is not None:
                self._task.cancel()
        except Exception:
            pass
        self._task = None
        # Reflect cancellation in loading state
        try:
            self.loading.set(False)
        except Exception:
            pass


def use_resource(fetcher: Callable[..., Awaitable[R]]) -> Resource[R]:
    """Create an async Resource with loading/error states and cancellation.

    The provided `fetcher` should be an async function returning the data value.
    If it accepts a `signal` keyword argument, an AbortSignal will be passed for
    cancellation support when available.
    """
    return Resource(fetcher)
