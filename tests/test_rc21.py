"""Solid 2.0 RC.21 alignment (RFC 0006): `on_flush`, `from_source`, and `create_owner`'s removal."""

import asyncio
from collections.abc import Callable
from typing import Any

import pytest

import wybthon
from wybthon import (
    Memo,
    create_effect,
    create_memo,
    create_root,
    create_signal,
    flush,
    from_source,
    is_dev_mode,
    is_pending,
    latest,
    on_flush,
    set_dev_mode,
)


def _owned(make: Callable[[], Memo[Any]]) -> tuple[Memo[Any], Callable[[], None]]:
    """A memo under its own root, and the root's dispose."""
    disposers: list[Callable[[], None]] = []

    def body(dispose: Callable[[], None]) -> Memo[Any]:
        disposers.append(dispose)
        return make()

    return create_root(body), disposers[0]


async def _tick(n: int = 5) -> None:
    for _ in range(n):
        flush()
        await asyncio.sleep(0)
    flush()


# ---------------------------------------------------------------------------
# on_flush
# ---------------------------------------------------------------------------


def test_on_flush_runs_once_after_the_pending_flush(wyb):
    count, set_count = create_signal(0)
    seen: list[Any] = []

    def effect(value: int) -> None:
        seen.append(("effect", value))

    create_root(lambda dispose: create_effect(count, effect))
    flush()
    set_count(1)
    on_flush(lambda: seen.append(("flush", count())))
    assert seen == [("effect", 0)]
    flush()
    # After the flush's effects have run, reading the committed value.
    assert seen == [("effect", 0), ("effect", 1), ("flush", 1)]
    flush()
    assert seen == [("effect", 0), ("effect", 1), ("flush", 1)]


def test_a_write_in_on_flush_is_an_update_of_its_own(wyb):
    count, set_count = create_signal(0)
    seen: list[int] = []
    create_root(lambda dispose: create_effect(count, seen.append))
    flush()

    def bump() -> None:
        set_count(lambda n: n + 1)

    set_count(1)
    on_flush(bump)
    flush()
    # The write in the callback is staged for the next flush, not this one.
    assert count.peek() == 1 and seen == [0, 1]
    flush()
    assert seen == [0, 1, 2]


def test_on_flush_errors_are_logged_and_the_rest_still_run(wyb, capsys):
    seen: list[str] = []

    def broken() -> None:
        raise ValueError("nope")

    on_flush(broken)
    on_flush(lambda: seen.append("after"))
    flush()
    assert seen == ["after"]
    assert "on_flush callback raised: nope" in capsys.readouterr().err


def test_on_flush_in_a_computation_warns_in_dev_mode(wyb, capsys):
    previous = is_dev_mode()
    set_dev_mode(True)
    try:
        count, _ = create_signal(0)

        def body() -> int:
            on_flush(lambda: None)
            return count()

        memo = create_root(lambda dispose: create_memo(body))
        memo()
        flush()
    finally:
        set_dev_mode(previous)
    assert "on_flush() was called in a component body or computation" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# from_source
# ---------------------------------------------------------------------------


class _Emitter:
    """A push source: `subscribe(next, error, complete)` returning an unsubscribe callable."""

    def __init__(self) -> None:
        self.listeners: list[Any] = []
        self.unsubscribed = 0

    def __call__(self, next_: Any, error: Any, complete: Any) -> Any:
        entry = (next_, error, complete)
        self.listeners.append(entry)

        def unsubscribe() -> None:
            self.unsubscribed += 1
            self.listeners.remove(entry)

        return unsubscribe

    def emit(self, value: Any) -> None:
        for next_, _error, _complete in list(self.listeners):
            next_(value)

    def fail(self, error: BaseException) -> None:
        for _next, fail, _complete in list(self.listeners):
            fail(error)


def test_from_source_holds_the_latest_value_and_unsubscribes_on_dispose(wyb):
    source = _Emitter()

    async def main() -> None:
        value, dispose = _owned(lambda: create_memo(lambda: from_source(source)))
        await _tick()
        assert latest(value) is None and len(source.listeners) == 1
        source.emit(1)
        await _tick()
        assert value() == 1
        # Values pushed faster than the memo reads them: only the latest lands.
        source.emit(2)
        source.emit(3)
        await _tick()
        assert value() == 3
        dispose()
        await _tick()
        assert source.unsubscribed == 1 and not source.listeners

    asyncio.run(main())


def test_from_source_resubscribes_when_the_memo_reruns(wyb):
    sources = {1: _Emitter(), 2: _Emitter()}

    async def main() -> None:
        which, set_which = create_signal(1)
        value, _dispose = _owned(lambda: create_memo(lambda: from_source(sources[which()])))
        await _tick()
        sources[1].emit("a")
        await _tick()
        assert value() == "a"
        set_which(2)
        await _tick()
        assert sources[1].unsubscribed == 1
        sources[2].emit("b")
        await _tick()
        assert value() == "b" and not is_pending(value)

    asyncio.run(main())


def test_from_source_errors_reach_the_reader(wyb):
    source = _Emitter()

    async def main() -> None:
        value, _dispose = _owned(lambda: create_memo(lambda: from_source(source)))
        await _tick()
        source.emit(1)
        await _tick()
        source.fail(ValueError("closed"))
        await _tick()
        with pytest.raises(ValueError, match="closed"):
            value()

    asyncio.run(main())


def test_from_source_accepts_observables_and_async_iterables(wyb):
    class Disposable:
        def __init__(self, owner: "Observable") -> None:
            self.owner = owner

        def dispose(self) -> None:
            self.owner.disposed = True

    class Observable:
        disposed = False

        def subscribe(self, on_next: Any, on_error: Any, on_completed: Any) -> Disposable:
            on_next("first")
            return Disposable(self)

    async def numbers() -> Any:
        for n in range(3):
            yield n

    async def main() -> None:
        observable = Observable()
        pushed, dispose = _owned(lambda: create_memo(lambda: from_source(observable)))
        streamed, _dispose = _owned(lambda: create_memo(lambda: from_source(numbers())))
        await _tick()
        assert pushed() == "first"
        assert streamed() == 2
        dispose()
        await _tick()
        assert observable.disposed

    asyncio.run(main())


def test_create_owner_is_removed():
    # Solid 2.0 RC.21 dropped `createOwner`; `create_root` and `run_with_owner` replace it.
    assert not hasattr(wybthon, "create_owner")
    assert "create_owner" not in wybthon.__all__
