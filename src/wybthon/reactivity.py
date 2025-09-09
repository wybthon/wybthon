from __future__ import annotations

from typing import Any, Callable, Generic, Optional, Set, TypeVar, List, Awaitable


T = TypeVar("T")


_current_computation: Optional["Computation"] = None
_pending: Set["Computation"] = set()
_flush_scheduled: bool = False
_batch_depth: int = 0


def _schedule_flush() -> None:
    global _flush_scheduled
    if _flush_scheduled:
        return
    _flush_scheduled = True

    # Try microtask scheduling; fall back to setTimeout(0)
    try:
        from js import queueMicrotask  # type: ignore
        from pyodide.ffi import create_once_callable  # type: ignore

        queueMicrotask(create_once_callable(lambda: _flush()))
    except Exception:  # pragma: no cover
        # Try Pyodide setTimeout, else Python threading/asyncio fallback
        try:
            from js import setTimeout  # type: ignore
            from pyodide.ffi import create_once_callable  # type: ignore

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
    # Snapshot and clear to allow re-scheduling during runs
    pending = list(_pending)
    _pending.clear()
    for comp in pending:
        comp.run()


class Computation:
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
            signal._subscribers.add(self)

    def run(self) -> None:
        if self._is_disposed:
            return
        # Clear old subscriptions
        for s in list(self._deps):
            s._subscribers.discard(self)
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
        _pending.add(self)
        if _batch_depth == 0:
            _schedule_flush()

    def dispose(self) -> None:
        if self._is_disposed:
            return
        self._is_disposed = True
        for s in list(self._deps):
            s._subscribers.discard(self)
        self._deps.clear()
        while self._on_dispose:
            fn = self._on_dispose.pop()
            try:
                fn()
            except Exception:
                pass


class Signal(Generic[T]):
    def __init__(self, value: T) -> None:
        self._value: T = value
        self._subscribers: Set[Computation] = set()

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
    return Signal(value)


class _Computed(Generic[T]):
    def __init__(self, fn: Callable[[], T]) -> None:
        self._value_signal: Signal[T] = Signal(None)  # type: ignore[arg-type]

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
    return _Computed(fn)


def effect(fn: Callable[[], Any]) -> Computation:
    comp = Computation(fn)
    comp.run()
    return comp


def on_effect_cleanup(comp: Computation, fn: Callable[[], Any]) -> None:
    comp._on_dispose.append(fn)


class _Batch:
    def __enter__(self) -> None:
        global _batch_depth
        _batch_depth += 1

    def __exit__(self, exc_type, exc, tb) -> None:
        global _batch_depth
        _batch_depth -= 1
        if _batch_depth == 0 and _pending:
            _schedule_flush()


def batch() -> _Batch:
    return _Batch()


# -------------------- Async resource utility --------------------
R = TypeVar("R")


class Resource(Generic[R]):
    """Async resource wrapper with Signals for data, error, and loading.

    Use `reload()` to (re)fetch, `cancel()` to cancel the in-flight request.
    """

    def __init__(self, fetcher: Callable[..., Awaitable[R]]) -> None:
        # Lazily import to avoid import cycles at module import time
        import asyncio  # local import for Pyodide compatibility
        import inspect

        self._asyncio = asyncio
        self._inspect = inspect
        self._fetcher: Callable[..., Awaitable[R]] = fetcher
        self._task: Optional[asyncio.Task] = None  # type: ignore[name-defined]
        self._abort_controller: Any = None
        self._version: int = 0

        self.data: Signal[Optional[R]] = Signal(None)
        self.error: Signal[Optional[Any]] = Signal(None)
        self.loading: Signal[bool] = Signal(False)

        # Kick off initial load
        self.reload()

    def _make_abort_controller(self) -> Any:
        try:
            from js import AbortController  # type: ignore

            # In Pyodide, construct with .new()
            return AbortController.new()
        except Exception:
            return None

    async def _run(self, current_version: int, controller: Any) -> None:
        try:
            # If fetcher accepts a 'signal' kwarg, pass it; otherwise call without
            if self._inspect.signature(self._fetcher).parameters.get("signal") is not None:
                coro = self._fetcher(signal=getattr(controller, "signal", None))
            else:
                coro = self._fetcher()

            # Await the result (support both awaitable and plain values defensively)
            if self._inspect.isawaitable(coro):
                result = await coro  # type: ignore[misc]
            else:
                result = coro  # type: ignore[assignment]

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


def use_resource(fetcher: Callable[..., Awaitable[R]]) -> Resource[R]:
    """Create an async Resource with loading/error states and cancellation.

    The provided `fetcher` should be an async function returning the data value.
    If it accepts a `signal` keyword argument, an AbortSignal will be passed for
    cancellation support when available.
    """
    return Resource(fetcher)
