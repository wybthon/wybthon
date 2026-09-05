"""Mounted region identity, lifetimes, and bounded work."""

import asyncio

from conftest import collect_texts

from wybthon import (
    For,
    Repeat,
    Show,
    component,
    create_effect,
    create_memo,
    create_selector,
    create_signal,
    create_store,
    div,
    flush,
    on_cleanup,
    p,
    span,
)
from wybthon.diagnostics import profile


def texts(node):
    return [value for value in collect_texts(node) if value]


def test_store_append_and_swap_skip_full_list_work(wyb, root_element):
    rows, write = create_store([{"id": i} for i in range(1000)])
    created = []

    def row(item, index):
        created.append(item.id)
        return [span(lambda: str(item.id)), span(lambda: str(index()))]

    root = wyb["reconciler"].render(div(For(lambda: rows, row)), root_element)
    with profile() as append:
        write(lambda d: d.append({"id": 1000}))
        flush()
    assert append.counts["rows_created"] == 1
    assert append.counts["list_scanned"] == 0
    assert len(created) == 1001

    def swap(d):
        d[1], d[998] = d[998], d[1]

    with profile() as swapped:
        write(swap)
        flush()
    assert swapped.counts["rows_created"] == swapped.counts["list_scanned"] == 0
    assert texts(root_element.element)[2:4] == ["998", "1"]
    assert texts(root_element.element)[1996:1998] == ["1", "998"]
    root.dispose()


def test_fragment_rows_keep_scope_through_reorders(wyb, root_element):
    rows, write = create_store([{"id": 1}, {"id": 2}])
    count, set_count = create_signal(0)
    disposed = []

    def row(item, index):
        on_cleanup(lambda: disposed.append(item.id))
        return [span(lambda: str(item.id)), span(count)]

    root = wyb["reconciler"].render(div(For(lambda: rows, row)), root_element)
    write(lambda d: d.reverse())
    flush()
    set_count(3)
    flush()
    assert texts(root_element.element) == ["2", "3", "1", "3"]
    assert disposed == []
    root.dispose()
    assert sorted(disposed) == [1, 2]


def test_keyed_show_remounts_same_component_type(wyb, root_element):
    value, set_value = create_signal(1)
    created, disposed = [], []

    @component
    def Child():
        current = value.peek()
        created.append(current)
        on_cleanup(lambda: disposed.append(current))
        return p(str(current))

    root = wyb["reconciler"].render(Show(value, lambda _: Child(), keyed=True), root_element)
    set_value(2)
    flush()
    assert created == [1, 2]
    assert disposed == [1]
    assert texts(root_element.element) == ["2"]
    root.dispose()


def test_repeat_tail_growth_doesnt_scan_existing_rows(wyb, root_element):
    count, set_count = create_signal(1000)
    root = wyb["reconciler"].render(Repeat(count, lambda i: span(str(i))), root_element)
    with profile() as measured:
        set_count(1001)
        flush()
    assert measured.counts["rows_created"] == 1
    assert measured.counts["list_scanned"] == 0
    root.dispose()


def test_selector_keeps_shared_key_subscribers(wyb):
    selected, set_selected = create_signal(1)
    selector = create_selector(selected)
    first, second = [], []
    one = create_effect(lambda: selector(1), first.append)
    two = create_effect(lambda: selector(1), second.append)
    flush()
    one.dispose()
    flush()
    set_selected(2)
    flush()
    assert first == [True]
    assert second == [True, False]
    two.dispose()


def test_list_cleanup_waits_for_visible_transition(wyb, root_element):
    async def main():
        rows, write = create_store([1, 2])
        count, set_count = create_signal(0)
        gate = asyncio.Event()

        async def load():
            value = count()
            if value:
                await gate.wait()
            return value

        memo = create_memo(load)
        disposed = []

        def row(item, index):
            on_cleanup(lambda: disposed.append(item))
            return span(str(item))

        root = wyb["reconciler"].render(div(For(lambda: rows, row), p(memo)), root_element)

        def edit(d):
            d.pop()

        write(edit)
        set_count(1)
        flush()
        assert disposed == []
        assert texts(root_element.element) == ["1", "2", "0"]
        gate.set()
        await asyncio.sleep(0)
        flush()
        assert disposed == [2]
        root.dispose()
        memo.dispose()

    asyncio.run(main())


def test_random_store_edits_match_plain_list_and_keep_live_rows(wyb, root_element):
    import random

    rng = random.Random(782)
    expected = list(range(12))
    store, write = create_store([{"id": value} for value in expected])
    created, disposed = [], []

    def row(item, index):
        created.append(item.id)
        on_cleanup(lambda: disposed.append(item.id))
        return [span(lambda: str(item.id)), span(lambda: str(index()))]

    root = wyb["reconciler"].render(For(lambda: store, row), root_element)
    next_id = 12
    for _ in range(120):
        operation = rng.randrange(5) if expected else 0
        if operation == 0:
            index = rng.randrange(len(expected) + 1)
            expected.insert(index, next_id)

            def insert(d):
                d.insert(index, {"id": next_id})

            write(insert)
            next_id += 1
        elif operation == 1:
            index = rng.randrange(len(expected))
            del expected[index]

            def remove(d):
                del d[index]

            write(remove)
        elif operation == 2:
            expected.reverse()
            write(lambda d: d.reverse())
        elif operation == 3:
            a, b = rng.randrange(len(expected)), rng.randrange(len(expected))
            expected[a], expected[b] = expected[b], expected[a]

            def swap(d):
                d[a], d[b] = d[b], d[a]

            write(swap)
        else:
            expected.sort()
            write(lambda d: d.sort(key=lambda item: item.id))
        flush()
        assert texts(root_element.element) == [
            text for i, value in enumerate(expected) for text in (str(value), str(i))
        ]
        assert set(created) - set(disposed) == set(expected)
    root.dispose()
    assert sorted(created) == sorted(disposed)
