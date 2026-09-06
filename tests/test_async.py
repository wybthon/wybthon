"""Async computations, actions, and optimistic values."""

from __future__ import annotations

import asyncio

import pytest

from wybthon.reactivity import (
    NotReadyError,
    action,
    create_effect,
    create_memo,
    create_optimistic,
    create_root,
    create_signal,
    create_tracked_effect,
    flush,
    is_pending,
    latest,
    refresh,
    resolve,
)


async def _tick(n: int = 3) -> None:
    """Alternate flushes and event-loop turns so async runs can start and settle."""
    for _ in range(n):
        flush()
        await asyncio.sleep(0)
    flush()


def _observe(accessor) -> list:
    """Keep an async memo observed so it recomputes eagerly, like a hole would."""
    seen: list = []
    create_root(lambda d: create_effect(lambda: latest(accessor), lambda v: seen.append(v)))
    return seen


# ---------------------------------------------------------------------------
# Async memos
# ---------------------------------------------------------------------------


def test_async_memo_raises_not_ready_then_resolves(wyb):
    async def main() -> None:
        gate = asyncio.Event()

        async def load() -> str:
            await gate.wait()
            return "data"

        user = create_root(lambda d: create_memo(load))
        with pytest.raises(NotReadyError):
            _ = user()
        assert latest(user) is None
        assert is_pending(user)
        gate.set()
        await _tick()
        assert user() == "data"
        assert not is_pending(user)

    asyncio.run(main())


def test_async_memo_tracks_reads_before_and_after_await(wyb):
    async def main() -> None:
        a, set_a = create_signal(1)
        b, set_b = create_signal(10)
        runs: list[int] = []

        async def compute() -> int:
            x = a()
            await asyncio.sleep(0)
            y = b()
            runs.append(1)
            return x + y

        total = create_root(lambda d: create_memo(compute))
        _observe(total)
        assert await resolve(total) == 11
        set_b(20)
        await _tick()
        assert total() == 21
        set_a(2)
        await _tick()
        assert total() == 22
        assert len(runs) == 3

    asyncio.run(main())


def test_async_memo_serves_stale_value_while_revalidating(wyb):
    async def main() -> None:
        uid, set_uid = create_signal(1)
        gates = {1: asyncio.Event(), 2: asyncio.Event()}

        async def load() -> str:
            i = uid()
            await gates[i].wait()
            return f"user{i}"

        user = create_root(lambda d: create_memo(load))
        _observe(user)
        gates[1].set()
        assert await resolve(user) == "user1"
        set_uid(2)
        await _tick()
        assert user() == "user1"
        assert is_pending(user)
        gates[2].set()
        await _tick()
        assert user() == "user2"
        assert not is_pending(user)

    asyncio.run(main())


def test_refresh_is_quiet_and_awaitable(wyb):
    async def main() -> None:
        calls: list[int] = []

        async def load() -> int:
            calls.append(1)
            await asyncio.sleep(0)
            return len(calls)

        n = create_root(lambda d: create_memo(load))
        assert await resolve(n) == 1
        pending_seen: list[bool] = []
        create_root(lambda d: create_effect(lambda: is_pending(n), pending_seen.append))
        flush()
        value = await refresh(n)
        assert value == 2
        assert n() == 2
        await _tick()
        # The effect re-ran when the value changed, but pending never went True.
        assert pending_seen and True not in pending_seen

    asyncio.run(main())


def test_refresh_rejects_non_memo(wyb):
    with pytest.raises(TypeError):
        refresh(42)


def test_async_generator_memo_streams_values(wyb):
    async def main() -> None:
        async def ticker():
            for i in range(3):
                yield i
                await asyncio.sleep(0)

        m = create_root(lambda d: create_memo(ticker))
        seen: list[int] = []
        create_root(lambda d: create_effect(lambda: latest(m), lambda v: seen.append(v)))
        for _ in range(8):
            await asyncio.sleep(0)
            flush()
        assert m() == 2
        assert seen[-1] == 2
        assert 0 in seen or 1 in seen

    asyncio.run(main())


def test_resolve_rejects_when_memo_raises(wyb):
    async def main() -> None:
        async def bad() -> int:
            await asyncio.sleep(0)
            raise ValueError("nope")

        m = create_root(lambda d: create_memo(bad))
        with pytest.raises(ValueError):
            await resolve(m)

    asyncio.run(main())


def test_async_effect_body_awaits_without_blocking(wyb):
    async def main() -> None:
        count, set_count = create_signal(0)
        seen: list[int] = []

        async def body() -> None:
            v = count()
            await asyncio.sleep(0)
            seen.append(v)

        create_root(lambda d: create_tracked_effect(body))
        await _tick()
        set_count(1)
        await _tick()
        assert seen == [0, 1]

    asyncio.run(main())


def test_sync_memo_reading_not_ready_source_is_itself_not_ready(wyb):
    async def main() -> None:
        gate = asyncio.Event()

        async def load() -> int:
            await gate.wait()
            return 5

        base = create_root(lambda d: create_memo(load))
        doubled = create_root(lambda d: create_memo(lambda: base() * 2))
        with pytest.raises(NotReadyError):
            doubled()
        assert latest(doubled) is None
        gate.set()
        await _tick()
        assert doubled() == 10

    asyncio.run(main())


# ---------------------------------------------------------------------------
# Actions and optimistic values
# ---------------------------------------------------------------------------


def test_sync_action_returns_result_and_is_never_pending(wyb):
    @action
    def add(a: int, b: int) -> int:
        return a + b

    assert add(1, 2) == 3
    assert add.pending() is False
    assert repr(add) == "Action(add)"


def test_async_action_pending_and_result(wyb):
    async def main() -> None:
        gate = asyncio.Event()

        @action
        async def save(value: int) -> int:
            await gate.wait()
            return value * 2

        fut = save(21)
        flush()
        assert save.pending() is True
        gate.set()
        await _tick()
        assert await fut == 42
        assert save.pending() is False

    asyncio.run(main())


def test_async_action_error_propagates_to_awaiter(wyb):
    async def main() -> None:
        @action
        async def fail() -> None:
            await asyncio.sleep(0)
            raise RuntimeError("failed")

        with pytest.raises(RuntimeError):
            await fail()
        await _tick()
        assert fail.pending() is False

    asyncio.run(main())


def test_optimistic_override_reverts_when_action_settles(wyb):
    async def main() -> None:
        likes, set_likes = create_signal(1)
        shown, set_shown = create_optimistic(likes)
        gate = asyncio.Event()

        @action
        async def like() -> None:
            set_shown(lambda n: n + 1)
            await gate.wait()
            set_likes(2)

        assert shown() == 1
        fut = like()
        # The write happens synchronously before the first await; like any
        # write it becomes visible at the next flush.
        flush()
        assert shown() == 2
        assert is_pending(shown)
        gate.set()
        await _tick()
        await fut
        await _tick()
        assert shown() == 2
        assert likes() == 2
        assert not is_pending(shown)

    asyncio.run(main())


def test_optimistic_plain_value_source(wyb):
    shown, set_shown = create_optimistic("a")
    assert shown() == "a"
    assert shown.peek() == "a"
    set_shown("b")
    flush()
    assert shown() == "b"


def test_optimistic_tracked_by_memo(wyb):
    async def main() -> None:
        base, _ = create_signal(0)
        shown, set_shown = create_optimistic(base)
        label = create_root(lambda d: create_memo(lambda: f"n={shown()}"))
        assert label() == "n=0"
        gate = asyncio.Event()

        @action
        async def bump() -> None:
            set_shown(5)
            await gate.wait()

        fut = bump()
        flush()
        assert label() == "n=5"
        gate.set()
        await fut
        await _tick()
        assert label() == "n=0"

    asyncio.run(main())
