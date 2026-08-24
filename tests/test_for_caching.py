"""Tests for the fine-grained For list rendering (all keying modes).

The mapping callback must run exactly once per unique item; list
changes move cached DOM instead of re-rendering rows; row-local
reactive scopes survive list updates and are disposed on removal.
"""

import wybthon as _wybthon_pkg  # noqa: F401
from wybthon.vnode import h


def _li_nodes(ul):
    return [n for n in ul.childNodes if getattr(n, "tag", None) == "li"]


def _li_texts(ul):
    return [n.childNodes[0].nodeValue for n in _li_nodes(ul)]


def _setup(wyb, root_element, items_getter, row_fn, **for_kwargs):
    rec, flow = wyb["reconciler"], wyb["flow"]
    rec.render(h("ul", {}, flow.For(each=items_getter, children=row_fn, **for_kwargs)), root_element)
    return root_element.element.childNodes[0]


def test_for_maps_each_item_once(wyb, root_element):
    reactivity = wyb["reactivity"]
    a, b, c = {"id": 1, "t": "A"}, {"id": 2, "t": "B"}, {"id": 3, "t": "C"}
    items, set_items = reactivity.create_signal([a, b, c])
    calls = []

    def row(item, idx):
        calls.append(item()["t"])
        return h("li", {}, item()["t"])

    ul = _setup(wyb, root_element, items, row)
    assert calls == ["A", "B", "C"]
    assert _li_texts(ul) == ["A", "B", "C"]

    # Reorder: no new mapping calls, same DOM nodes moved.
    before_ids = {id(n) for n in _li_nodes(ul)}
    set_items([c, a, b])
    reactivity.flush()
    assert calls == ["A", "B", "C"]
    assert _li_texts(ul) == ["C", "A", "B"]
    assert {id(n) for n in _li_nodes(ul)} == before_ids


def test_for_append_maps_only_new_item(wyb, root_element):
    reactivity = wyb["reactivity"]
    a, b = {"t": "A"}, {"t": "B"}
    items, set_items = reactivity.create_signal([a, b])
    calls = []

    def row(item, idx):
        calls.append(item()["t"])
        return h("li", {}, item()["t"])

    ul = _setup(wyb, root_element, items, row)
    assert calls == ["A", "B"]

    c = {"t": "C"}
    set_items([a, b, c])
    reactivity.flush()
    assert calls == ["A", "B", "C"]
    assert _li_texts(ul) == ["A", "B", "C"]


def test_for_remove_disposes_row_scope(wyb, root_element):
    reactivity = wyb["reactivity"]
    a, b = {"t": "A"}, {"t": "B"}
    items, set_items = reactivity.create_signal([a, b])
    cleanups = []

    def row(item, idx):
        reactivity.on_cleanup(lambda: cleanups.append(item()["t"]))
        return h("li", {}, item()["t"])

    ul = _setup(wyb, root_element, items, row)
    set_items([b])
    reactivity.flush()
    assert cleanups == ["A"]
    assert _li_texts(ul) == ["B"]


def test_for_row_reactivity_survives_list_updates(wyb, root_element):
    """Row-local reactive prop bindings keep working after the list changes."""
    reactivity = wyb["reactivity"]
    a, b = {"id": 1, "t": "A"}, {"id": 2, "t": "B"}
    items, set_items = reactivity.create_signal([a, b])
    selected, set_selected = reactivity.create_signal(None)
    is_selected = reactivity.create_selector(selected)

    def row(item, idx):
        iid = item()["id"]
        return h("li", {"class": lambda: "on" if is_selected(iid) else ""}, item()["t"])

    ul = _setup(wyb, root_element, items, row)

    set_selected(2)
    reactivity.flush()
    assert [n.attributes.get("class") for n in _li_nodes(ul)] == ["", "on"]

    # Mutate the list, then change selection: bindings must still fire.
    c = {"id": 3, "t": "C"}
    set_items([a, b, c])
    set_selected(3)
    reactivity.flush()
    assert [n.attributes.get("class") for n in _li_nodes(ul)] == ["", "", "on"]

    set_items([b, c])
    set_selected(2)
    reactivity.flush()
    assert [n.attributes.get("class") for n in _li_nodes(ul)] == ["on", ""]


def test_for_index_getter_updates_on_reorder(wyb, root_element):
    reactivity = wyb["reactivity"]
    a, b = {"t": "A"}, {"t": "B"}
    items, set_items = reactivity.create_signal([a, b])

    def row(item, idx):
        return h("li", {}, lambda: f"{idx()}:{item()['t']}")

    ul = _setup(wyb, root_element, items, row)
    assert _li_texts(ul) == ["0:A", "1:B"]

    set_items([b, a])
    reactivity.flush()
    assert _li_texts(ul) == ["0:B", "1:A"]


def test_for_fallback_when_empty(wyb, root_element):
    reactivity = wyb["reactivity"]
    rec, flow = wyb["reconciler"], wyb["flow"]
    items, set_items = reactivity.create_signal([{"t": "A"}])

    rec.render(
        h(
            "div",
            {},
            flow.For(
                each=items,
                children=lambda item, idx: h("li", {}, item()["t"]),
                fallback=lambda: h("p", {}, "empty"),
            ),
        ),
        root_element,
    )
    from conftest import collect_texts

    assert "A" in collect_texts(root_element.element)
    set_items([])
    reactivity.flush()
    texts = collect_texts(root_element.element)
    assert "empty" in texts and "A" not in texts


def test_for_keyed_mode_updates_row_in_place(wyb, root_element):
    """With ``key=``, a fresh object with the same key keeps its row.

    The mapping callback must not re-run; the row's ``item`` getter
    updates instead (server-refresh pattern).
    """
    reactivity = wyb["reactivity"]
    items, set_items = reactivity.create_signal([{"id": 1, "t": "A"}, {"id": 2, "t": "B"}])
    calls = []

    def row(item, idx):
        calls.append(item()["id"])
        return h("li", {}, lambda: item()["t"])

    ul = _setup(wyb, root_element, items, row, key=lambda it: it["id"])
    assert calls == [1, 2]
    assert _li_texts(ul) == ["A", "B"]

    # Fresh objects, same keys, one changed title: rows update in place.
    before_ids = [id(n) for n in _li_nodes(ul)]
    set_items([{"id": 1, "t": "A2"}, {"id": 2, "t": "B"}])
    reactivity.flush()
    assert calls == [1, 2], "keyed refresh must not re-run the mapping callback"
    assert _li_texts(ul) == ["A2", "B"]
    assert [id(n) for n in _li_nodes(ul)] == before_ids


def test_for_index_mode_slots_render_once_and_update_in_place(wyb, root_element):
    """``key="index"`` gives per-position slots (the old Index component)."""
    reactivity = wyb["reactivity"]
    rec, flow = wyb["reconciler"], wyb["flow"]
    items, set_items = reactivity.create_signal(["A", "B"])
    calls = []

    def slot(item, idx):
        calls.append(idx())
        return h("li", {}, item)

    rec.render(h("ul", {}, flow.For(each=items, children=slot, key="index")), root_element)
    ul = root_element.element.childNodes[0]
    assert calls == [0, 1]
    assert _li_texts(ul) == ["A", "B"]

    # Values change in place: no new slot renders, same DOM nodes.
    before_ids = [id(n) for n in _li_nodes(ul)]
    set_items(["X", "Y"])
    reactivity.flush()
    assert calls == [0, 1]
    assert _li_texts(ul) == ["X", "Y"]
    assert [id(n) for n in _li_nodes(ul)] == before_ids

    # Growing creates exactly one new slot.
    set_items(["X", "Y", "Z"])
    reactivity.flush()
    assert calls == [0, 1, 2]
    assert _li_texts(ul) == ["X", "Y", "Z"]

    # Shrinking disposes the extra slot without re-rendering others.
    set_items(["X"])
    reactivity.flush()
    assert calls == [0, 1, 2]
    assert _li_texts(ul) == ["X"]


def test_repeat_renders_by_count(wyb, root_element):
    """Repeat mounts/disposes tail slots only; no list diffing."""
    reactivity = wyb["reactivity"]
    rec, flow = wyb["reconciler"], wyb["flow"]
    count, set_count = reactivity.create_signal(2)
    calls = []

    def slot(i):
        calls.append(i)
        return h("li", {}, f"#{i}")

    rec.render(h("ul", {}, flow.Repeat(times=count, children=slot)), root_element)
    ul = root_element.element.childNodes[0]
    assert calls == [0, 1]
    assert _li_texts(ul) == ["#0", "#1"]

    before_ids = [id(n) for n in _li_nodes(ul)]
    set_count(4)
    reactivity.flush()
    assert calls == [0, 1, 2, 3], "growing renders only the new tail slots"
    assert _li_texts(ul) == ["#0", "#1", "#2", "#3"]
    assert [id(n) for n in _li_nodes(ul)][:2] == before_ids

    set_count(1)
    reactivity.flush()
    assert calls == [0, 1, 2, 3], "shrinking renders nothing new"
    assert _li_texts(ul) == ["#0"]


def test_repeat_fallback_when_zero(wyb, root_element):
    reactivity = wyb["reactivity"]
    rec, flow = wyb["reconciler"], wyb["flow"]
    count, set_count = reactivity.create_signal(1)

    rec.render(
        h(
            "div",
            {},
            flow.Repeat(
                times=count,
                children=lambda i: h("li", {}, f"#{i}"),
                fallback=lambda: h("p", {}, "none"),
            ),
        ),
        root_element,
    )
    from conftest import collect_texts

    assert "#0" in collect_texts(root_element.element)
    set_count(0)
    reactivity.flush()
    texts = collect_texts(root_element.element)
    assert "none" in texts and "#0" not in texts
