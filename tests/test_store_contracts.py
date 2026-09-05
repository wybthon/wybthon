"""Store consistency, persistent sequence, and derived readiness contracts."""

import asyncio
import random
from collections.abc import Mapping, Sequence

import pytest

from wybthon import action, create_effect, create_signal, flush, is_pending, refresh
from wybthon._vector import Vector
from wybthon.store import DraftExpiredError, create_projection, create_store, deep, snapshot


def test_reads_dont_depend_on_observation_history(wyb):
    store, write = create_store({"a": 0, "b": 0, "rows": [1]})
    assert store.a == 0
    write(lambda d: (d.update(a=1, b=1), d.rows.append(2)) and None)
    assert (store.a, store.b, len(store.rows), list(store.rows)) == (0, 0, 1, [1])
    values = []
    create_effect(lambda: store.b, values.append)
    flush()
    assert (store.a, store.b, list(store.rows)) == (1, 1, [1, 2])
    assert values == [1]


def test_entity_moves_preserve_identity_and_field_tracking(wyb):
    store, write = create_store([{"id": "a", "n": 1}, {"id": "b", "n": 2}])
    a, b = store
    values = []
    create_effect(lambda: a.n, values.append)
    flush()
    write(lambda d: d.reverse())
    flush()
    assert store[0] is b and store[1] is a
    assert values == [1]
    write(lambda d: setattr(d[1], "n", 3))
    flush()
    assert a.n == 3
    assert values == [1, 3]


def test_drafts_expire_and_failed_edits_are_atomic(wyb):
    store, write = create_store({"n": 0, "nested": {"v": 1}})
    escaped = []

    def edit(d):
        escaped.extend([d, d.nested])
        d.n = 3
        d.nested.v = 5
        raise ValueError("abort")

    with pytest.raises(ValueError, match="abort"):
        write(edit)
    flush()
    assert snapshot(store) == {"n": 0, "nested": {"v": 1}}
    for draft in escaped:
        with pytest.raises(DraftExpiredError):
            len(draft)
        with pytest.raises(DraftExpiredError):
            draft["new"] = 1


def test_successful_draft_expires(wyb):
    store, write = create_store([])
    escaped = []
    write(lambda d: escaped.append(d))
    with pytest.raises(DraftExpiredError):
        escaped[0].append(1)
    assert snapshot(store) == []


def test_subtree_tracking_and_detached_snapshots(wyb):
    store, write = create_store({"left": {"n": 0}, "right": {"n": 0}})
    values = []
    create_effect(lambda: deep(store.left), values.append)
    flush()
    write(lambda d: setattr(d.right, "n", 1))
    flush()
    assert values == [{"n": 0}]
    copied = snapshot(store)
    copied["left"]["n"] = 42
    assert store.left.n == 0
    write(lambda d: setattr(d.left, "n", 2))
    flush()
    assert values == [{"n": 0}, {"n": 2}]


def test_negative_indices_and_membership_are_precise(wyb):
    rows, write = create_store([1, 2])
    values = []
    create_effect(lambda: rows[-1], values.append)
    flush()
    write(lambda d: d.append(3))
    flush()
    assert values == [2, 3]
    store, update = create_store({"a": 1})
    flags = []
    create_effect(lambda: "a" in store, flags.append)
    flush()
    update(lambda d: d.update(a=2))
    flush()
    assert flags == [True]
    assert isinstance(store, Mapping) and isinstance(rows, Sequence)


def test_list_journals_describe_only_new_edits(wyb):
    rows, write = create_store([1, 2, 3])
    state = rows._wyb_list_state()
    write(lambda d: d.append(4))
    flush()
    changes = rows._wyb_changes_since(state.revision)
    assert len(changes) == 1
    assert (changes[0].kind, changes[0].index, changes[0].added) == ("splice", 3, (4,))
    assert list(state.data) == [1, 2, 3]
    assert list(rows) == [1, 2, 3, 4]


def test_persistent_vector_random_operations():
    rng = random.Random(9071)
    expected = list(range(2100))
    vector = Vector(expected)
    original = vector
    for _ in range(1500):
        op = rng.randrange(4)
        if op == 0 or not expected:
            value = rng.randrange(10000)
            expected.append(value)
            vector = vector.append(value)
        elif op == 1:
            expected.pop()
            vector = vector.pop()
        elif op == 2:
            index, value = rng.randrange(len(expected)), rng.randrange(10000)
            expected[index] = value
            vector = vector.set(index, value)
        else:
            start = rng.randrange(len(expected))
            delete = min(rng.randrange(5), len(expected) - start)
            values = [rng.randrange(10000) for _ in range(rng.randrange(4))]
            expected[start : start + delete] = values
            vector = vector.splice(start, delete, values)
        assert list(vector) == expected
        assert vector[-1] == expected[-1]
    assert list(original) == list(range(2100))
    appended = original.append(2100)
    assert appended._tree[0] is original._tree[0]


def test_async_projection_readiness_refresh_and_cancel(wyb):
    async def main():
        gate = asyncio.Event()
        runs = []

        async def load():
            runs.append(len(runs) + 1)
            await gate.wait()
            return {"n": len(runs)}

        projection = create_projection(load, {"n": 0})
        assert is_pending(lambda: projection.n)
        gate.set()
        await asyncio.sleep(0)
        flush()
        assert projection.n == 1
        gate.clear()
        refreshed = refresh(projection)
        assert not is_pending(lambda: projection.n)
        assert projection.n == 1

        async def wait():
            return await refreshed

        task = asyncio.create_task(wait())
        await asyncio.sleep(0)
        assert not task.done()
        gate.set()
        assert await task is projection
        flush()
        assert projection.n == 2

    asyncio.run(main())


def test_unobserved_properties_keep_revealed_transition_view(wyb):
    async def main():
        store, write = create_store({"a": 0, "b": 0})
        gate = asyncio.Event()

        @action
        async def change():
            write(lambda d: d.update(a=1, b=1))
            assert store.a == 1  # An action sees its own staged writes.
            await gate.wait()

        future = change()
        flush()
        assert store.a == store.b == 0
        gate.set()
        await future
        flush()
        assert store.a == store.b == 1

    asyncio.run(main())


def test_projection_stream_errors_and_cancellation(wyb):
    async def main():
        gate = asyncio.Event()
        closed = []

        async def stream():
            try:
                yield {"n": 1}
                await gate.wait()
                yield {"n": 2}
            finally:
                closed.append(True)

        projection = create_projection(stream, {"n": 0})
        flush()
        assert projection.n == 1
        gate.set()
        for _ in range(4):
            await asyncio.sleep(0)
            flush()
        assert projection.n == 2
        assert closed == [True]

        async def broken():
            await asyncio.sleep(0)
            raise ValueError("projection failed")

        failed = create_projection(broken, {"n": 0})
        for _ in range(3):
            await asyncio.sleep(0)
            flush()
        with pytest.raises(ValueError, match="projection failed"):
            _ = failed.n

    asyncio.run(main())


def test_optimistic_store_until_reads_authoritative_state_and_rebases(wyb):
    from wybthon import create_optimistic_store, until

    async def main():
        base, set_base = create_signal({"n": 0, "other": 0})
        store, optimistic = create_optimistic_store(base)
        observed = []
        gate = asyncio.Event()

        @action
        async def update():
            optimistic(lambda d: setattr(d, "n", d.n + 1))
            await until(lambda: store.n >= 2)
            observed.append(store.n)
            await gate.wait()

        future = update()
        flush()
        assert store.n == 1
        set_base({"n": 1, "other": 1})
        flush()
        await asyncio.sleep(0)
        assert store.n == 2 and store.other == 1
        assert observed == []
        set_base({"n": 2, "other": 2})
        flush()
        for _ in range(3):
            await asyncio.sleep(0)
        assert observed == [3]
        gate.set()
        await future
        flush()
        assert snapshot(store) == {"n": 2, "other": 2}

    asyncio.run(main())
