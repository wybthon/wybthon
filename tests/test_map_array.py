"""Tests for map_array / index_array / create_selector reactive primitives."""

import time

from conftest import collect_texts

from wybthon.reactivity import (
    create_effect,
    create_root,
    create_selector,
    create_signal,
    index_array,
    map_array,
    on_cleanup,
)

# ---------------------------------------------------------------------------
# map_array — basic behaviour
# ---------------------------------------------------------------------------


def test_map_array_initial_mapping():
    items, _ = create_signal(["A", "B", "C"])
    mapped = map_array(items, lambda item, idx: f"{idx()}: {item()}")
    assert mapped() == ["0: A", "1: B", "2: C"]


def test_map_array_empty_source():
    items, _ = create_signal([])
    mapped = map_array(items, lambda item, idx: item())
    assert mapped() == []


def test_map_array_none_source():
    items, _ = create_signal(None)
    mapped = map_array(items, lambda item, idx: item())
    assert mapped() == []


def test_map_array_reactive_update():
    items, set_items = create_signal(["X", "Y"])
    mapped = map_array(items, lambda item, idx: item())
    assert mapped() == ["X", "Y"]

    set_items(["A", "B", "C"])
    time.sleep(0.05)
    assert mapped() == ["A", "B", "C"]


def test_map_array_item_removal():
    a, b, c = object(), object(), object()
    items, set_items = create_signal([a, b, c])
    mapped = map_array(items, lambda item, idx: id(item()))

    initial = mapped()
    assert len(initial) == 3

    set_items([a, c])
    time.sleep(0.05)
    result = mapped()
    assert len(result) == 2
    assert result[0] == id(a)
    assert result[1] == id(c)


def test_map_array_item_reorder_preserves_identity():
    a, b, c = object(), object(), object()
    items, set_items = create_signal([a, b, c])

    call_count = [0]

    def map_fn(item, idx):
        call_count[0] += 1
        return id(item())

    mapped = map_array(items, map_fn)
    initial = mapped()
    assert call_count[0] == 3

    set_items([c, a, b])
    time.sleep(0.05)

    reordered = mapped()
    assert set(reordered) == set(initial)
    assert call_count[0] == 3


def test_map_array_index_updates_on_reorder():
    a, b, c = object(), object(), object()
    items, set_items = create_signal([a, b, c])

    index_signals: list = []

    def map_fn(item, idx):
        index_signals.append(idx)
        return idx

    mapped = map_array(items, map_fn)
    mapped()

    set_items([c, a, b])
    time.sleep(0.05)
    mapped()

    assert index_signals[0]() == 1
    assert index_signals[1]() == 2
    assert index_signals[2]() == 0


# ---------------------------------------------------------------------------
# map_array — per-item disposal
# ---------------------------------------------------------------------------


def test_map_array_disposes_removed_items():
    a, b, c = object(), object(), object()
    items, set_items = create_signal([a, b, c])
    disposed = []

    def map_fn(item, idx):
        on_cleanup(lambda _i=idx(): disposed.append(_i))
        return item()

    result = create_root(lambda dispose: map_array(items, map_fn))
    result()

    set_items([a])
    time.sleep(0.05)
    result()

    assert 1 in disposed
    assert 2 in disposed


def test_map_array_disposes_all_on_empty():
    a, b = object(), object()
    items, set_items = create_signal([a, b])
    disposed = [0]

    def map_fn(item, idx):
        on_cleanup(lambda: disposed.__setitem__(0, disposed[0] + 1))
        return item()

    result = create_root(lambda dispose: map_array(items, map_fn))
    result()

    set_items([])
    time.sleep(0.05)
    result()

    assert disposed[0] == 2


# ---------------------------------------------------------------------------
# index_array — basic behaviour
# ---------------------------------------------------------------------------


def test_index_array_initial():
    items, _ = create_signal(["A", "B", "C"])
    mapped = index_array(items, lambda item, idx: f"[{idx}] {item()}")
    assert mapped() == ["[0] A", "[1] B", "[2] C"]


def test_index_array_empty():
    items, _ = create_signal([])
    mapped = index_array(items, lambda item, idx: item())
    assert mapped() == []


def test_index_array_none_source():
    items, _ = create_signal(None)
    mapped = index_array(items, lambda item, idx: item())
    assert mapped() == []


def test_index_array_item_value_update():
    """When a value at an existing index changes, the item signal updates."""
    items, set_items = create_signal(["A", "B"])
    item_getters: list = []

    def map_fn(item, idx):
        item_getters.append(item)
        return item

    mapped = index_array(items, map_fn)
    mapped()

    assert item_getters[0]() == "A"
    assert item_getters[1]() == "B"

    set_items(["X", "Y"])
    time.sleep(0.05)
    mapped()

    assert item_getters[0]() == "X"
    assert item_getters[1]() == "Y"


def test_index_array_grow():
    items, set_items = create_signal(["A"])
    call_count = [0]

    def map_fn(item, idx):
        call_count[0] += 1
        return item

    mapped = index_array(items, map_fn)
    mapped()
    assert call_count[0] == 1

    set_items(["A", "B", "C"])
    time.sleep(0.05)
    mapped()
    assert call_count[0] == 3


def test_index_array_shrink_disposes():
    items, set_items = create_signal(["A", "B", "C"])
    disposed = [0]

    def map_fn(item, idx):
        on_cleanup(lambda: disposed.__setitem__(0, disposed[0] + 1))
        return item

    result = create_root(lambda dispose: index_array(items, map_fn))
    result()

    set_items(["A"])
    time.sleep(0.05)
    result()

    assert disposed[0] == 2


# ---------------------------------------------------------------------------
# create_selector
# ---------------------------------------------------------------------------


def test_create_selector_basic():
    selected, set_selected = create_signal(1)
    is_selected = create_selector(selected)

    assert is_selected(1) is True
    assert is_selected(2) is False
    assert is_selected(3) is False


def test_create_selector_updates():
    selected, set_selected = create_signal(1)
    is_selected = create_selector(selected)

    assert is_selected(1) is True
    assert is_selected(2) is False

    set_selected(2)
    time.sleep(0.05)

    assert is_selected(1) is False
    assert is_selected(2) is True


def test_create_selector_notifies_only_affected_keys():
    selected, set_selected = create_signal("a")
    is_selected = create_selector(selected)
    runs = {"a": 0, "b": 0, "c": 0}

    def track(key):
        def eff():
            is_selected(key)
            runs[key] += 1

        return eff

    create_root(lambda dispose: (create_effect(track("a")), create_effect(track("b")), create_effect(track("c"))))

    assert runs == {"a": 1, "b": 1, "c": 1}

    set_selected("b")
    time.sleep(0.05)

    assert runs["a"] == 2
    assert runs["b"] == 2
    assert runs["c"] == 1


def test_create_selector_same_value_no_op():
    selected, set_selected = create_signal(1)
    is_selected = create_selector(selected)
    runs = [0]

    def eff():
        is_selected(1)
        runs[0] += 1

    create_root(lambda dispose: create_effect(eff))
    assert runs[0] == 1

    set_selected(1)
    time.sleep(0.05)
    assert runs[0] == 1


# ---------------------------------------------------------------------------
# map_array / index_array rendered through VDOM
# ---------------------------------------------------------------------------


def test_map_array_in_component(wyb, root_element):
    """map_array works inside a component's setup phase."""
    vdom, reactivity = wyb["vdom"], wyb["reactivity"]
    a, b, c = object(), object(), object()
    items, set_items = reactivity.create_signal([a, b, c])

    labels = {id(a): "alpha", id(b): "beta", id(c): "gamma"}

    def App(props):
        mapped = reactivity.map_array(items, lambda item, idx: labels.get(id(item()), "?"))

        def render():
            return vdom.h("ul", {}, *[vdom.h("li", {}, v) for v in mapped()])

        return render

    vdom.render(vdom.h(App, {}), root_element)
    texts = collect_texts(root_element.element)
    assert "alpha" in texts
    assert "beta" in texts
    assert "gamma" in texts


def test_index_array_in_component(wyb, root_element):
    """index_array works inside a component's setup phase."""
    vdom, reactivity = wyb["vdom"], wyb["reactivity"]
    items, set_items = reactivity.create_signal(["A", "B"])

    def App(props):
        mapped = reactivity.index_array(items, lambda item, idx: f"[{idx}] {item()}")

        def render():
            return vdom.h("ul", {}, *[vdom.h("li", {}, v) for v in mapped()])

        return render

    vdom.render(vdom.h(App, {}), root_element)
    texts = collect_texts(root_element.element)
    assert "[0] A" in texts
    assert "[1] B" in texts
