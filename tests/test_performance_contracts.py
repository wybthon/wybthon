"""Compatibility at the boundaries of compact storage and list fast paths."""

import asyncio
import gc
import weakref

import pytest

from wybthon import For, action, create_memo, create_signal, create_store, deep, flush, map_array, on_cleanup, span
from wybthon._vector import Vector
from wybthon.diagnostics import profile
from wybthon.store import DraftExpiredError


@pytest.mark.parametrize("size", [0, 1, 31, 32, 33, 1023, 1024, 1025, 32768, 32769])
def test_bulk_vectors_preserve_values_across_tree_boundaries(size):
    values = list(range(size))
    vector = Vector(iter(values))
    assert list(vector) == values
    assert list(vector.append("tail")) == [*values, "tail"]
    assert vector[::-17] == values[::-17]
    if size:
        assert list(vector.pop()) == values[:-1]
        assert list(vector.set(-1, "last")) == [*values[:-1], "last"]
    for start in sorted({0, min(1, size), min(32, size), min(1024, size), size}):
        trimmed = vector.splice(start, size - start, ())
        assert list(trimmed) == values[:start]
        assert list(trimmed.append("next")) == [*values[:start], "next"]
        assert list(vector) == values
    middle = size // 2
    assert list(vector.splice(middle, min(3, size - middle), iter(["a", "b"]))) == (
        values[:middle] + ["a", "b"] + values[middle + min(3, size - middle) :]
    )


def test_shared_store_entities_notify_each_remaining_parent(wyb):
    store, write = create_store({"entity": {"n": 0}, "left": [], "right": []})

    def share(d):
        d.left.extend([d.entity, d.entity])
        d.right.append(d.entity)

    write(share)
    flush()
    calls = {"left": 0, "right": 0}

    def read(side):
        calls[side] += 1
        return deep(store[side])

    left = create_memo(lambda: read("left"))
    right = create_memo(lambda: read("right"))
    assert left() == [{"n": 0}, {"n": 0}]
    assert right() == [{"n": 0}]
    write(lambda d: (d.left.pop(), None)[1])
    flush()
    assert left() == [{"n": 0}]
    write(lambda d: setattr(d.entity, "n", 1))
    flush()
    assert left() == right() == [{"n": 1}]
    write(lambda d: d.left.clear())
    flush()
    assert left() == []
    before = calls.copy()
    write(lambda d: setattr(d.entity, "n", 2))
    flush()
    assert left() == []
    assert right() == [{"n": 2}]
    assert calls == {"left": before["left"], "right": before["right"] + 1}
    assert store.right[0] is store.entity


def test_repeated_links_to_one_parent_keep_deep_subscription(wyb):
    store, write = create_store([{"n": 0}])
    write(lambda d: d.append(d[0]))
    flush()
    memo = create_memo(lambda: deep(store))
    assert memo() == [{"n": 0}, {"n": 0}]
    write(lambda d: (d.pop(), None)[1])
    flush()
    assert memo() == [{"n": 0}]
    write(lambda d: setattr(d[0], "n", 1))
    flush()
    assert memo() == [{"n": 1}]


@pytest.mark.parametrize("shared", [False, True])
def test_retained_entity_doesnt_retain_its_parents(wyb, shared):
    store, write = create_store({"entity": {"n": 0}, "other": []})
    entity = store.entity
    if shared:
        write(lambda d: d.other.append(d.entity))
        flush()
    parent = weakref.ref(store._node)
    other = weakref.ref(store.other._node)
    del store, write
    gc.collect()
    assert parent() is None and other() is None
    assert entity.n == 0


def test_map_array_prefix_keys_run_once_and_replacements_stay_reactive(wyb):
    source, write = create_signal([{"id": 1, "v": "a"}, {"id": 2, "v": "b"}])
    keys, disposed = [], []

    def key(item):
        keys.append(item["id"])
        return item["id"]

    def row(item, index):
        identity = item.peek()["id"]
        on_cleanup(lambda: disposed.append(identity))
        return create_memo(lambda: (item()["v"], index()))

    mapped = map_array(source, row, keyed=key)
    first, second = mapped()
    assert (first(), second()) == (("a", 0), ("b", 1))
    keys.clear()
    write([{"id": 1, "v": "new"}, {"id": 3, "v": "c"}, {"id": 2, "v": "b"}])
    flush()
    assert keys == [1, 3, 2]
    assert mapped()[0] is first and mapped()[2] is second
    assert (first(), second()) == (("new", 0), ("b", 2))
    assert disposed == []
    mapped.dispose()
    assert sorted(disposed) == [1, 2, 3]


def test_map_array_append_truncate_and_duplicate_occurrence_identity(wyb):
    source, write = create_signal([1, 1, 2])
    disposed = []

    def row(item, index):
        token = object()
        on_cleanup(lambda: disposed.append(token))
        return token, index

    mapped = map_array(source, row, fallback=lambda: "empty")
    first, second, third = mapped()
    write([1, 2, 1, 3])
    flush()
    assert mapped()[:3] == [first, third, second]
    assert [entry[1]() for entry in mapped()] == [0, 1, 2, 3]
    write([1, 2])
    flush()
    assert mapped() == [first, third]
    assert second[0] in disposed and first[0] not in disposed
    write([])
    flush()
    assert mapped() == ["empty"]
    mapped.dispose()


def test_draft_clear_batches_disposal_and_preserves_transaction_boundaries(wyb, root_element):
    store, write = create_store(list(range(1000)))
    disposed = []

    def row(item, index):
        on_cleanup(lambda: disposed.append(item))
        return span(str(item))

    root = wyb["reconciler"].render(For(lambda: store, row), root_element)
    escaped = []

    def clear(draft):
        escaped.append(draft)
        draft.clear()
        assert len(draft) == 0
        assert len(store) == 1000

    with profile() as measured:
        write(clear)
        assert disposed == []
        flush()
    assert len(store) == 0
    assert disposed == list(reversed(range(1000)))
    assert measured.counts["list_edits"] == 1
    assert measured.counts["commits"] == 1
    with pytest.raises(DraftExpiredError):
        escaped[0].clear()
    write(lambda draft: (draft.clear(), draft.append(42)) and None)
    flush()
    assert list(store) == [42]

    def abort(draft):
        draft.clear()
        raise ValueError("abort")

    with pytest.raises(ValueError, match="abort"):
        write(abort)
    flush()
    assert list(store) == [42]
    root.dispose()


def test_draft_clear_and_refill_retains_cleanup_order_through_a_transition(wyb, root_element):
    async def main():
        store, write = create_store([1, 2, 3])
        created, disposed = [], []

        def row(item, index):
            created.append(item)
            on_cleanup(lambda: disposed.append(item))
            return span(str(item))

        root = wyb["reconciler"].render(For(lambda: store, row), root_element)
        gate = asyncio.Event()

        @action
        async def replace():
            write(lambda draft: (draft.clear(), draft.extend([1, 2, 3])) and None)
            await gate.wait()

        future = replace()
        flush()
        assert list(store) == [1, 2, 3]
        assert disposed == [] and created == [1, 2, 3]
        gate.set()
        await future
        flush()
        assert disposed == [3, 2, 1]
        assert created == [1, 2, 3, 1, 2, 3]
        assert list(store) == [1, 2, 3]
        root.dispose()

    asyncio.run(main())
