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
    create_projection,
    create_signal,
    create_store,
    flush,
    get_owner,
    html,
    on_cleanup,
)
from wybthon.diagnostics import profile
from wybthon.kernel import OP_DISPOSE, OP_DISPOSE_RANGE, OP_MOVE_RANGE


def texts(node):
    return [value for value in collect_texts(node) if value and value.strip()]


def test_store_append_and_swap_skip_full_list_work(wyb, root_element):
    rows, write = create_store([{"id": i} for i in range(1000)])
    created = []

    def row(item, index):
        created.append(item.id)
        return html(t"<span>{item.id}</span><span>{index()}</span>")

    root = wyb["reconciler"].render(html(t"<div>{For(rows, row)}</div>"), root_element)
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
        return html(t"<span>{item.id}</span><span>{count}</span>")

    root = wyb["reconciler"].render(html(t"<div>{For(rows, row)}</div>"), root_element)
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
        return html(t"<p>{current}</p>")

    def branch(_):
        return Child()

    root = wyb["reconciler"].render(html(t"{Show(value, branch, keyed=True)}"), root_element)
    set_value(2)
    flush()
    assert created == [1, 2]
    assert disposed == [1]
    assert texts(root_element.element) == ["2"]
    root.dispose()


def test_repeat_tail_growth_doesnt_scan_existing_rows(wyb, root_element):
    count, set_count = create_signal(1000)

    def row(i):
        return html(t"<span>{i}</span>")

    root = wyb["reconciler"].render(html(t"{Repeat(count, row)}"), root_element)
    with profile() as measured:
        set_count(1001)
        flush()
    assert measured.counts["rows_created"] == 1
    assert measured.counts["list_scanned"] == 0
    root.dispose()


def test_projection_selection_keeps_shared_key_subscribers(wyb):
    selected, set_selected = create_signal(1)
    is_selected = create_projection(lambda: {} if selected() is None else {selected(): True})
    first, second = [], []
    one = create_effect(lambda: bool(is_selected.get(1)), first.append)
    two = create_effect(lambda: bool(is_selected.get(1)), second.append)
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
        return html(t"<span data-token={token}>{f'{item}:{index()}'}</span>")

    root = wyb["reconciler"].render(html(t"{For(values, row)}"), root_element)

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
        return html(t"<span>{item.id}</span>")

    root = wyb["reconciler"].render(html(t"{For(store, row)}"), root_element)

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

    def row(item, index):
        return html(t"<span>{item()['label']}</span>")

    def key(item):
        return item["id"]

    root = wyb["reconciler"].render(html(t"{For(rows, row, keyed=key)}"), root_element)
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
            # The list and request share a dependency. Independent writes in
            # the same batch no longer wait for each other.
            len(rows)
            value = count()
            if value:
                await gate.wait()
            return value

        memo = create_memo(load)
        disposed = []

        def row(item, index):
            on_cleanup(lambda: disposed.append(item))
            return html(t"<span>{item}</span>")

        root = wyb["reconciler"].render(html(t"<div>{For(rows, row)}<p>{memo}</p></div>"), root_element)

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
        return html(t"<span>{item.id}</span><span>{index()}</span>")

    root = wyb["reconciler"].render(html(t"{For(store, row)}"), root_element)
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


def test_projection_selection_in_rows_rerenders_only_changed_rows(wyb, root_element):
    selected, set_selected = create_signal(None)
    is_selected = create_projection(lambda: {} if selected() is None else {selected(): True})
    rows, _ = create_signal(list(range(50)))
    evaluations = []

    def row(item, index):
        def cls():
            evaluations.append(item)
            return "danger" if is_selected.get(item) else ""

        return html(t"<span class={cls}>{item}</span>")

    root = wyb["reconciler"].render(html(t"<div>{For(rows, row)}</div>"), root_element)
    assert len(evaluations) == 50
    evaluations.clear()
    set_selected(3)
    flush()
    assert evaluations == [3]
    evaluations.clear()
    set_selected(7)
    flush()
    assert sorted(evaluations) == [3, 7]
    spans = [n for n in root_element.element.childNodes[0].childNodes if n.tag == "span"]
    assert spans[7].attributes["class"] == "danger"
    assert "class" not in spans[3].attributes or spans[3].attributes["class"] == ""
    root.dispose()


# ---------------------------------------------------------------------------
# Keyed matching: swaps, permutations, and lazy row indices
# ---------------------------------------------------------------------------


def _mount_rows(wyb, root_element, values, *, read_index=False):
    """Mount `For(values, row)` in a <ul>; returns (root, list element, created items)."""
    created = []

    def row(item, i):
        created.append(item)
        if read_index:
            return html(t"<li>{item}:{i()}</li>")
        return html(t"<li>{item}</li>")

    root = wyb["reconciler"].render(html(t"<ul>{For(values, row)}</ul>"), root_element)
    return root, root_element.element.childNodes[0], created


def _items(ul):
    return [node for node in ul.childNodes if node.tag == "li"]


def _labels(ul):
    return ["".join(collect_texts(node)) for node in _items(ul)]


def _guard_generic_matching(wyb, monkeypatch):
    """Record calls into the generic child reconciler and per-row updates."""
    calls = []
    region = wyb["reconciler"]._reconcile_children
    monkeypatch.setattr(
        wyb["reconciler"], "_reconcile_children", lambda *a, **k: (calls.append("children"), region(*a, **k))[1]
    )
    from wybthon import _regions

    update = _regions._ListRegion.update_row
    monkeypatch.setattr(_regions._ListRegion, "update_row", lambda self, *a: (calls.append("row"), update(self, *a))[1])
    return calls


def test_swapping_two_rows_is_two_moves_without_generic_matching(wyb, root_element, monkeypatch):
    values, write = create_signal(list(range(100)))
    root, ul, created = _mount_rows(wyb, root_element, values)
    before = _items(ul)
    calls = _guard_generic_matching(wyb, monkeypatch)
    swapped = list(range(100))
    swapped[1], swapped[98] = swapped[98], swapped[1]
    with profile() as measured:
        write(swapped)
        flush()
    assert measured.counts[f"op_{OP_MOVE_RANGE}"] == 2
    assert measured.counts["dom_ops"] == 2
    assert measured.counts["rows_created"] == 0
    assert calls == []
    after = _items(ul)
    assert _labels(ul) == [str(v) for v in swapped]
    assert after[1] is before[98] and after[98] is before[1]
    assert [node for i, node in enumerate(after) if i not in (1, 98)] == [
        node for i, node in enumerate(before) if i not in (1, 98)
    ]
    assert len(created) == 100
    root.dispose()


def test_swapping_the_first_and_last_rows_is_two_moves(wyb, root_element, monkeypatch):
    values, write = create_signal(list(range(20)))
    root, ul, _created = _mount_rows(wyb, root_element, values)
    before = _items(ul)
    calls = _guard_generic_matching(wyb, monkeypatch)
    swapped = [19, *range(1, 19), 0]
    with profile() as measured:
        write(swapped)
        flush()
    assert _labels(ul) == [str(v) for v in swapped]
    assert _items(ul)[0] is before[19] and _items(ul)[19] is before[0]
    assert measured.counts["rows_created"] == 0
    assert measured.counts[f"op_{OP_MOVE_RANGE}"] == 2
    assert calls == []
    root.dispose()


def test_reversal_and_permutations_keep_rows_and_order(wyb, root_element):
    import random

    rng = random.Random(4417)
    initial = list(range(30))
    values, write = create_signal(initial)
    root, ul, created = _mount_rows(wyb, root_element, values, read_index=True)
    nodes = dict(zip(initial, _items(ul)))
    orders = [list(reversed(initial)), initial]
    for _ in range(25):
        order = list(initial)
        rng.shuffle(order)
        orders.append(order)
    # Adjacent swaps, rotations, and a swap next to the ends.
    orders += [[1, 0, *initial[2:]], [*initial[1:], 0], [29, *initial[:29]], [0, 28, *initial[2:28], 1, 29]]
    for order in orders:
        with profile() as measured:
            write(order)
            flush()
        assert measured.counts["rows_created"] == 0
        assert _labels(ul) == [f"{value}:{i}" for i, value in enumerate(order)]
        assert _items(ul) == [nodes[value] for value in order]
    assert len(created) == 30
    root.dispose()


def test_removing_the_first_of_many_rows_disposes_one_row_and_moves_nothing(wyb, root_element):
    values, write = create_signal(list(range(1000)))
    disposed = []

    def row(item, i):
        on_cleanup(lambda: disposed.append(item))
        return html(t"<li>{item}</li>")

    root = wyb["reconciler"].render(html(t"<ul>{For(values, row)}</ul>"), root_element)
    ul = root_element.element.childNodes[0]
    kept = _items(ul)[1:]
    with profile() as measured:
        write(values()[1:])
        flush()
    assert disposed == [0]
    assert measured.counts["rows_created"] == 0
    assert measured.counts[f"op_{OP_MOVE_RANGE}"] == 0
    assert measured.counts[f"op_{OP_DISPOSE_RANGE}"] + measured.counts[f"op_{OP_DISPOSE}"] == 1
    assert measured.counts["dom_ops"] == 1
    assert _items(ul) == kept
    assert _labels(ul)[:2] == ["1", "2"]
    root.dispose()


def test_row_index_read_in_markup_updates_when_rows_move(wyb, root_element):
    values, write = create_signal(["a", "b", "c", "d"])
    root, ul, _created = _mount_rows(wyb, root_element, values, read_index=True)
    assert _labels(ul) == ["a:0", "b:1", "c:2", "d:3"]
    write(["a", "c", "b", "d"])
    flush()
    assert _labels(ul) == ["a:0", "c:1", "b:2", "d:3"]
    write(["d", "c", "b", "a"])
    flush()
    assert _labels(ul) == ["d:0", "c:1", "b:2", "a:3"]
    write(["c", "b", "a"])
    flush()
    assert _labels(ul) == ["c:0", "b:1", "a:2"]
    write(["a", "c", "b", "a2"])
    flush()
    assert _labels(ul) == ["a:0", "c:1", "b:2", "a2:3"]
    root.dispose()


def test_rows_are_their_own_owners_and_allocate_an_index_signal_only_when_read(wyb, root_element):
    values, write = create_signal(["a", "b", "c"])
    rows = {}

    def row(item, i):
        assert get_owner() is i
        rows[item] = i
        if item == "b":
            return html(t"<li>{item}:{i()}</li>")
        return html(t"<li>{item}</li>")

    root = wyb["reconciler"].render(html(t"<ul>{For(values, row)}</ul>"), root_element)
    assert rows["a"]._index_signal is None
    assert rows["c"]._index_signal is None
    assert rows["b"]._index_signal is not None
    write(["c", "b", "a"])
    flush()
    # Moving rows keeps the plain index current without allocating a signal.
    assert rows["a"]._index_signal is None and rows["a"].peek() == 2
    assert rows["c"]._index_signal is None and rows["c"].peek() == 0
    # An untracked read returns the integer without allocating.
    assert rows["a"]() == 2 and rows["a"]._index_signal is None
    seen = []
    effect = create_effect(lambda: rows["a"](), seen.append)
    flush()
    assert rows["a"]._index_signal is not None
    write(["a", "b", "c"])
    flush()
    assert seen == [2, 0]
    effect.dispose()
    root.dispose()
    assert all(row._disposed for row in rows.values())
