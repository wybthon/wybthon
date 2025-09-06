from __future__ import annotations

from typing import Any, Callable, Generic, Optional, Set, TypeVar, List


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
        from js import setTimeout  # type: ignore
        from pyodide.ffi import create_once_callable  # type: ignore

        setTimeout(create_once_callable(lambda: _flush()), 0)


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
