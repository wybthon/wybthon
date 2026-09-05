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


def test_generic_edits_preserve_duplicate_occurrence_identity(wyb, root_element):
    import random
    from collections import defaultdict, deque

    rng = random.Random(8273)
    initial = list(range(12))
    values, write = create_signal(initial)
    serial = 0
    disposed = []

    def row(item, index):
        nonlocal serial
        serial += 1
        token = serial
        on_cleanup(lambda: disposed.append(token))
        return span(lambda: f"{item}:{index()}", data_token=token)

    root = wyb["reconciler"].render(For(values, row), root_element)

    def elements():
        return [node for node in root_element.element.childNodes if node.tag == "span"]

    previous = list(zip(initial, elements()))
    # Include duplicates introduced before an otherwise unchanged suffix.
    examples = [[11, *initial[1:]], [11, 11], [11], [1, 2, 1], [2, 1], initial]
    examples += [[rng.randrange(9) for _ in range(rng.randrange(20))] for _ in range(100)]
    for current in examples:
        available = defaultdict(deque)
        for value, node in previous:
            available[value].append(node)
        write(current)
        flush()
        nodes = elements()
        assert len(nodes) == len(current)
        for index, (value, node) in enumerate(zip(current, nodes)):
            if available[value]:
                assert node is available[value].popleft()
            assert collect_texts(node) == [f"{value}:{index}"]
        previous = list(zip(current, nodes))
    root.dispose()
    assert len(disposed) == serial
    assert len(set(disposed)) == serial


def test_unused_indices_can_become_reactive_after_edits(wyb, root_element):
    store, write = create_store([{"id": i} for i in range(5)])
    indices = {}

    def row(item, index):
        indices[item.id] = index
        return span(str(item.id))

    root = wyb["reconciler"].render(For(lambda: store, row), root_element)

    def remove_first(draft):
        del draft[0]

    write(remove_first)
    flush()
    assert [indices[i]() for i in range(1, 5)] == [0, 1, 2, 3]
    seen = []
    effect = create_effect(lambda: [indices[i]() for i in range(1, 5)], seen.append)
    flush()
    write(lambda draft: draft.reverse())
    flush()
    assert seen == [[0, 1, 2, 3], [3, 2, 1, 0]]
    effect.dispose()
    root.dispose()


def test_equal_custom_key_replacement_can_change_on_a_later_write(wyb, root_element):
    original = {"id": 1, "label": "first"}
    rows, write = create_signal([original], equals=False)
    root = wyb["reconciler"].render(
        For(rows, lambda item, index: span(lambda: item()["label"]), keyed=lambda item: item["id"]),
        root_element,
    )
    replacement = dict(original)
    write([replacement])
    flush()
    replacement["label"] = "second"
    write([replacement])
    flush()
    assert texts(root_element.element) == ["second"]
    root.dispose()


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
