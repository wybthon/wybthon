"""Observable ownership and asyncio contracts for the reactive runtime."""

import asyncio

import pytest

from wybthon import (
    action,
    create_effect,
    create_memo,
    create_root,
    create_signal,
    flush,
    is_pending,
    on_cleanup,
    resolve,
    until,
)


def test_committed_effect_cleanup_waits_for_transition(wyb):
    async def main():
        source, set_source = create_signal(0)
        gate = asyncio.Event()
        events = []

        async def load():
            value = source()
            if value:
                await gate.wait()
            return value

        memo = create_memo(load)
        effect = create_effect(
            lambda: (source(), memo()),
            lambda value: (events.append(("apply", value)), lambda: events.append(("cleanup", value)))[1],
        )
        flush()
        assert events == [("apply", (0, 0))]
        set_source(1)
        flush()
        assert events == [("apply", (0, 0))]
        gate.set()
        await asyncio.sleep(0)
        flush()
        assert events == [("apply", (0, 0)), ("cleanup", (0, 0)), ("apply", (1, 1))]
        effect.dispose()
        memo.dispose()
        assert events[-1] == ("cleanup", (1, 1))

    asyncio.run(main())


def test_normal_read_isnt_downgraded_by_pending_probe(wyb):
    async def main():
        value, set_value = create_signal(0)
        gate = asyncio.Event()

        @action
        async def change():
            set_value(1)
            await gate.wait()

        shown = []
        create_effect(lambda: (value(), is_pending(value)), shown.append)
        flush()
        future = change()
        flush()
        assert value() == 0
        assert shown == [(0, False)]
        gate.set()
        await future
        flush()
        assert shown[-1] == (1, False)

    asyncio.run(main())


def test_nested_roots_are_owned_and_detachment_is_explicit(wyb):
    events = []

    def setup(dispose):
        create_root(lambda _: on_cleanup(lambda: events.append("owned")))
        detached = create_root(lambda stop: (on_cleanup(lambda: events.append("detached")), stop)[1], detached=True)
        return dispose, detached

    dispose, detached = create_root(setup)
    dispose()
    assert events == ["owned"]
    detached()
    assert events == ["owned", "detached"]


def test_dispose_cancels_waiter_and_runs_async_finally(wyb):
    async def main():
        gate = asyncio.Event()
        events = []

        async def load():
            try:
                await gate.wait()
            finally:
                await asyncio.sleep(0)
                events.append("closed")

        memo = create_memo(load)
        assert len(gate._waiters) == 1
        memo.dispose()
        for _ in range(4):
            await asyncio.sleep(0)
        assert not gate._waiters
        assert events == ["closed"]

    asyncio.run(main())


def test_async_computation_uses_real_task_and_preserves_tracking(wyb):
    async def main():
        source, set_source = create_signal(1)
        caller = asyncio.current_task()
        tasks = []

        async def load():
            tasks.append(asyncio.current_task())
            async with asyncio.timeout(1):
                await asyncio.sleep(0)
                async with asyncio.TaskGroup() as group:
                    child = group.create_task(asyncio.sleep(0, result=2))
                return source() * child.result()

        memo = create_memo(load)
        assert await resolve(memo) == 2
        assert tasks[0] is not caller
        set_source(3)
        flush()
        assert await resolve(memo) == 6
        memo.dispose()

    asyncio.run(main())


def test_action_cancel_stops_body_and_clears_pending(wyb):
    async def main():
        gate = asyncio.Event()
        events = []

        @action
        async def work():
            try:
                await gate.wait()
                events.append("late")
            finally:
                events.append("closed")

        future = work()
        flush()
        assert work.pending()
        future.cancel()
        for _ in range(4):
            await asyncio.sleep(0)
        flush()
        assert events == ["closed"]
        assert not work.pending()
        assert not gate._waiters

    asyncio.run(main())


def test_cancelled_until_releases_subscription(wyb):
    async def main():
        source, _ = create_signal(False)

        async def wait():
            await until(source)

        task = asyncio.create_task(wait())
        await asyncio.sleep(0)
        assert source._observers
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not source._observers

    asyncio.run(main())


def test_cancelled_resolve_releases_subscription(wyb):
    async def main():
        gate = asyncio.Event()
        memo = create_memo(gate.wait)

        async def wait():
            await resolve(memo)

        task = asyncio.create_task(wait())
        await asyncio.sleep(0)
        assert memo._observers
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not memo._observers
        memo.dispose()

    asyncio.run(main())


def test_map_array_duplicate_keys_dispose_and_held_lifetimes(wyb):
    from wybthon import map_array

    async def main():
        source, write = create_signal([1, 1, 2])
        disposed = []
        mapped = map_array(source, lambda item, index: (on_cleanup(lambda: disposed.append(item)), item)[1])
        assert mapped() == [1, 1, 2]
        gate = asyncio.Event()

        @action
        async def remove():
            write([2])
            await gate.wait()

        future = remove()
        flush()
        assert mapped() == [1, 1, 2]
        assert disposed == []
        gate.set()
        await future
        flush()
        assert mapped() == [2]
        assert disposed == [1, 1]
        mapped.dispose()
        assert disposed == [1, 1, 2]

    asyncio.run(main())


def test_literal_callables_are_data_and_lazy_memo_reactivates(wyb):
    from wybthon import literal

    def handler():
        return "value"

    state, write = create_signal(None)
    write(literal(handler))
    flush()
    assert state() is handler
    source, update = create_signal(1)
    memo = create_memo(lambda: source() * 2, lazy=True)
    values = []
    observer = create_effect(memo, values.append)
    flush()
    observer.dispose()
    flush()
    update(3)
    flush()
    assert memo() == 6


def test_apply_cleanup_is_untracked_and_failure_doesnt_skip_disposal(wyb, capsys):
    value, write = create_signal(0)
    cleaned = []

    def apply(current):
        on_cleanup(lambda: cleaned.append("scope"))

        def cleanup():
            write(1)
            raise ValueError("cleanup failed")

        return cleanup

    effect = create_effect(value, apply)
    flush()
    observer = create_memo(lambda: (effect.dispose(), 42)[1])
    assert observer() == 42
    flush()
    assert value() == 1
    assert cleaned == ["scope"]
    assert effect._disposed
    assert "cleanup failed" in capsys.readouterr().err
    assert value not in (observer._sources or {})
