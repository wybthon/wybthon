"""Tests for the fine-grained For/Index list rendering.

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


def _setup(wyb, root_element, items_getter, row_fn):
    rec, flow = wyb["reconciler"], wyb["flow"]
    rec.render(h("ul", {}, flow.For(each=items_getter, children=row_fn)), root_element)
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
    assert [n.attributes.get("class") for n in _li_nodes(ul)] == ["", "on"]

    # Mutate the list, then change selection: bindings must still fire.
    c = {"id": 3, "t": "C"}
    set_items([a, b, c])
    set_selected(3)
    assert [n.attributes.get("class") for n in _li_nodes(ul)] == ["", "", "on"]

    set_items([b, c])
    set_selected(2)
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
    texts = collect_texts(root_element.element)
    assert "empty" in texts and "A" not in texts


def test_index_slots_render_once_and_update_in_place(wyb, root_element):
    reactivity = wyb["reactivity"]
    rec, flow = wyb["reconciler"], wyb["flow"]
    items, set_items = reactivity.create_signal(["A", "B"])
    calls = []

    def slot(item, idx):
        calls.append(idx)
        return h("li", {}, item)

    rec.render(h("ul", {}, flow.Index(each=items, children=slot)), root_element)
    ul = root_element.element.childNodes[0]
    assert calls == [0, 1]
    assert _li_texts(ul) == ["A", "B"]

    # Values change in place: no new slot renders, same DOM nodes.
    before_ids = [id(n) for n in _li_nodes(ul)]
    set_items(["X", "Y"])
    assert calls == [0, 1]
    assert _li_texts(ul) == ["X", "Y"]
    assert [id(n) for n in _li_nodes(ul)] == before_ids

    # Growing creates exactly one new slot.
    set_items(["X", "Y", "Z"])
    assert calls == [0, 1, 2]
    assert _li_texts(ul) == ["X", "Y", "Z"]

    # Shrinking disposes the extra slot without re-rendering others.
    set_items(["X"])
    assert calls == [0, 1, 2]
    assert _li_texts(ul) == ["X"]
