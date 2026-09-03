"""Rendering tests against the in-memory stub DOM via the batched kernel."""

import pytest
from conftest import StubNode, collect_texts

from wybthon.html import button, div, em, h1, input_, li, p, span, ul
from wybthon.reactivity import create_signal
from wybthon.svg import circle, foreignObject, svg
from wybthon.vnode import NS_SVG, Fragment, hole


def _elements(node):
    return [n for n in node.childNodes if n.tag]


def _texts(node):
    return [t for t in collect_texts(node) if t]


def _record_ops(monkeypatch, backend):
    recorded = []
    original = backend.apply

    def apply(ops):
        recorded.extend(ops)
        original(ops)

    monkeypatch.setattr(backend, "apply", apply)
    return recorded


# ---------------------------------------------------------------------------
# Mounting
# ---------------------------------------------------------------------------


def test_mount_text_at_root(wyb, root_element):
    wyb["reconciler"].render("hello", root_element)
    container = root_element.element
    assert len(container.childNodes) == 1
    node = container.childNodes[0]
    assert node._is_text and node.nodeValue == "hello"


def test_mount_element_with_text(wyb, root_element):
    wyb["reconciler"].render(div("hi", id="x"), root_element)
    d = root_element.element.childNodes[0]
    assert d.tag == "div"
    assert d.attributes["id"] == "x"
    assert _texts(d) == ["hi"]


def test_mount_nested_tree(wyb, root_element):
    wyb["reconciler"].render(div(span("a"), p("b", em("c"))), root_element)
    d = root_element.element.childNodes[0]
    assert [n.tag for n in _elements(d)] == ["span", "p"]
    para = _elements(d)[1]
    assert para.childNodes[0].nodeValue == "b"
    assert _elements(para)[0].tag == "em"
    assert _texts(d) == ["a", "b", "c"]


def test_render_returns_root_and_dispose_clears_container(wyb, root_element):
    reconciler = wyb["reconciler"]
    backend = wyb["kernel"]._backend
    root = reconciler.render(div("x"), root_element)
    assert isinstance(root, reconciler.Root)
    assert root.container is root_element
    assert root.node_id == root_element.node_id
    assert backend.roots() == [root_element.element]

    root.dispose()
    assert root_element.element.childNodes == []
    assert backend.roots() == []
    root.dispose()  # idempotent


def test_render_twice_into_same_container_patches_in_place(wyb, root_element):
    render = wyb["reconciler"].render
    root1 = render(div("a", title="t1"), root_element)
    d = root_element.element.childNodes[0]
    root2 = render(div("b", title="t2"), root_element)
    assert root2 is root1
    assert len(root_element.element.childNodes) == 1
    assert root_element.element.childNodes[0] is d
    assert d.attributes["title"] == "t2"
    assert _texts(d) == ["b"]


def test_render_accepts_node_id_container(wyb, root_element):
    root = wyb["reconciler"].render(div("x"), root_element.node_id)
    assert root.container.element is root_element.element
    assert _texts(root_element.element) == ["x"]


# ---------------------------------------------------------------------------
# Patching text and attributes
# ---------------------------------------------------------------------------


def test_patch_text_reuses_text_node(wyb, root_element):
    render = wyb["reconciler"].render
    render(div("a"), root_element)
    text_node = root_element.element.childNodes[0].childNodes[0]
    render(div("b"), root_element)
    assert root_element.element.childNodes[0].childNodes[0] is text_node
    assert text_node.nodeValue == "b"


def test_patch_attribute_add_change_remove(wyb, root_element):
    render = wyb["reconciler"].render
    render(div(), root_element)
    d = root_element.element.childNodes[0]
    assert "title" not in d.attributes

    render(div(title="a"), root_element)
    assert d.attributes["title"] == "a"
    render(div(title="b"), root_element)
    assert d.attributes["title"] == "b"
    render(div(title=None), root_element)
    assert "title" not in d.attributes
    render(div(title="c"), root_element)
    render(div(), root_element)
    assert "title" not in d.attributes


def test_hyphenated_attribute_names(wyb, root_element):
    wyb["reconciler"].render(div(aria_label="Close", data_testid="root"), root_element)
    d = root_element.element.childNodes[0]
    assert d.attributes["aria-label"] == "Close"
    assert d.attributes["data-testid"] == "root"


def test_boolean_attributes(wyb, root_element):
    render = wyb["reconciler"].render
    render(button("go", disabled=True, draggable=True), root_element)
    b = root_element.element.childNodes[0]
    assert b.attributes["disabled"] == ""
    assert b.attributes["draggable"] == "true"

    render(button("go", disabled=False, draggable=False), root_element)
    assert "disabled" not in b.attributes
    assert "draggable" not in b.attributes


def test_dom_property_props(wyb, root_element):
    render = wyb["reconciler"].render
    render(input_(value="hi", checked=True), root_element)
    inp = root_element.element.childNodes[0]
    assert inp.value == "hi"
    assert inp.checked is True
    assert "value" not in inp.attributes
    assert "checked" not in inp.attributes

    render(input_(value="yo", checked=False), root_element)
    assert inp.value == "yo"
    assert inp.checked is False


# ---------------------------------------------------------------------------
# class / style
# ---------------------------------------------------------------------------


def test_class_as_str_list_dict(wyb, root_element):
    render = wyb["reconciler"].render
    render(div(class_="a b"), root_element)
    d = root_element.element.childNodes[0]
    assert d.attributes["class"] == "a b"

    render(div(class_=["x", None, "", "y"]), root_element)
    assert d.attributes["class"] == "x y"

    render(div(class_={"on": True, "off": False, "also": 1}), root_element)
    assert d.attributes["class"] == "on also"

    render(div(class_={"off": False}), root_element)
    assert "class" not in d.attributes


def test_class_dict_with_accessor_values_updates(wyb, root_element):
    flush = wyb["reactivity"].flush
    active, set_active = create_signal(False)
    wyb["reconciler"].render(div(class_={"base": True, "active": active}), root_element)
    d = root_element.element.childNodes[0]
    assert d.attributes["class"] == "base"

    set_active(True)
    flush()
    assert d.attributes["class"] == "base active"

    set_active(False)
    flush()
    assert d.attributes["class"] == "base"


def test_class_as_accessor_updates(wyb, root_element):
    flush = wyb["reactivity"].flush
    theme, set_theme = create_signal("light")
    wyb["reconciler"].render(div(class_=lambda: f"theme-{theme()}"), root_element)
    d = root_element.element.childNodes[0]
    assert d.attributes["class"] == "theme-light"
    set_theme("dark")
    flush()
    assert d.attributes["class"] == "theme-dark"


def test_style_dict_snake_camel_and_kebab_keys(wyb, root_element):
    render = wyb["reconciler"].render
    render(div(style={"background_color": "red", "fontSize": "12px", "margin-top": "1px"}), root_element)
    d = root_element.element.childNodes[0]
    assert d.style._props == {"background-color": "red", "font-size": "12px", "margin-top": "1px"}

    render(div(style={"background_color": "blue"}), root_element)
    assert d.style._props == {"background-color": "blue"}


def test_style_string(wyb, root_element):
    wyb["reconciler"].render(div(style="color: red"), root_element)
    d = root_element.element.childNodes[0]
    assert d.attributes["style"] == "color: red"


def test_style_dict_with_accessor_values_updates(wyb, root_element):
    flush = wyb["reactivity"].flush
    color, set_color = create_signal("red")
    wyb["reconciler"].render(div(style={"color": color, "display": "block"}), root_element)
    d = root_element.element.childNodes[0]
    assert d.style._props == {"color": "red", "display": "block"}
    set_color("blue")
    flush()
    assert d.style._props == {"color": "blue", "display": "block"}


# ---------------------------------------------------------------------------
# Reactive props
# ---------------------------------------------------------------------------


def test_reactive_attribute_updates_on_signal_write(wyb, root_element):
    flush = wyb["reactivity"].flush
    title, set_title = create_signal("one")
    wyb["reconciler"].render(div(title=title), root_element)
    d = root_element.element.childNodes[0]
    assert d.attributes["title"] == "one"
    set_title("two")
    flush()
    assert d.attributes["title"] == "two"


def test_reactive_boolean_attribute(wyb, root_element):
    flush = wyb["reactivity"].flush
    count, set_count = create_signal(0)
    wyb["reconciler"].render(button("go", disabled=lambda: count() >= 1), root_element)
    b = root_element.element.childNodes[0]
    assert "disabled" not in b.attributes
    set_count(1)
    flush()
    assert b.attributes["disabled"] == ""
    set_count(0)
    flush()
    assert "disabled" not in b.attributes


def test_reactive_props_update_independently(wyb, root_element, monkeypatch):
    kernel = wyb["kernel"]
    flush = wyb["reactivity"].flush
    title, set_title = create_signal("t1")
    ident, _set_ident = create_signal("i1")
    wyb["reconciler"].render(div(title=title, id=ident), root_element)
    d = root_element.element.childNodes[0]

    ops = _record_ops(monkeypatch, kernel._backend)
    set_title("t2")
    flush()
    set_attr_ops = [op for op in ops if op[0] == kernel.OP_SET_ATTR]
    assert set_attr_ops == [(kernel.OP_SET_ATTR, d._wyb_id, "title", "t2")]
    assert d.attributes == {"title": "t2", "id": "i1"}


def test_reactive_dom_property(wyb, root_element):
    flush = wyb["reactivity"].flush
    value, set_value = create_signal("a")
    wyb["reconciler"].render(input_(value=value), root_element)
    inp = root_element.element.childNodes[0]
    assert inp.value == "a"
    set_value("b")
    flush()
    assert inp.value == "b"


# ---------------------------------------------------------------------------
# Reactive holes
# ---------------------------------------------------------------------------


def test_hole_text_updates_reuse_text_node(wyb, root_element):
    flush = wyb["reactivity"].flush
    count, set_count = create_signal(0)
    wyb["reconciler"].render(div(lambda: f"n={count()}"), root_element)
    d = root_element.element.childNodes[0]
    text_node = [n for n in d.childNodes if n._is_text and n.nodeValue][0]
    assert text_node.nodeValue == "n=0"
    set_count(3)
    flush()
    assert text_node.nodeValue == "n=3"
    assert _texts(d) == ["n=3"]


def test_hole_switches_between_kinds(wyb, root_element):
    flush = wyb["reactivity"].flush
    content, set_content = create_signal("text")
    wyb["reconciler"].render(div(content), root_element)
    d = root_element.element.childNodes[0]
    assert _texts(d) == ["text"]
    assert _elements(d) == []

    set_content(span("el"))
    flush()
    assert [n.tag for n in _elements(d)] == ["span"]
    assert _texts(d) == ["el"]

    set_content(["a", span("b"), None])
    flush()
    assert _texts(d) == ["a", "b"]
    assert [n.tag for n in _elements(d)] == ["span"]

    set_content(None)
    flush()
    assert _texts(d) == []
    assert _elements(d) == []

    set_content("back")
    flush()
    assert _texts(d) == ["back"]


def test_explicit_hole_helper_renders(wyb, root_element):
    flush = wyb["reactivity"].flush
    name, set_name = create_signal("Ada")
    wyb["reconciler"].render(p(hole(lambda: f"Hi {name()}", key="greet")), root_element)
    para = root_element.element.childNodes[0]
    assert _texts(para) == ["Hi Ada"]
    set_name("Bob")
    flush()
    assert _texts(para) == ["Hi Bob"]


def test_hole_children_inside_static_siblings_keep_order(wyb, root_element):
    flush = wyb["reactivity"].flush
    mid, set_mid = create_signal("m1")
    wyb["reconciler"].render(div(span("first"), mid, span("last")), root_element)
    d = root_element.element.childNodes[0]
    assert _texts(d) == ["first", "m1", "last"]
    set_mid("m2")
    flush()
    assert _texts(d) == ["first", "m2", "last"]


# ---------------------------------------------------------------------------
# Lists and fragments
# ---------------------------------------------------------------------------


def test_keyed_list_reorder_moves_nodes(wyb, root_element):
    flush = wyb["reactivity"].flush
    order, set_order = create_signal(["a", "b", "c"])
    wyb["reconciler"].render(ul(lambda: [li(k, key=k) for k in order()]), root_element)
    lst = root_element.element.childNodes[0]
    before = {n.childNodes[0].nodeValue: id(n) for n in _elements(lst)}
    assert list(before) == ["a", "b", "c"]

    set_order(["c", "a", "b"])
    flush()
    after = {n.childNodes[0].nodeValue: id(n) for n in _elements(lst)}
    assert list(after) == ["c", "a", "b"]
    assert after == before


def test_keyed_list_add_and_remove(wyb, root_element):
    flush = wyb["reactivity"].flush
    order, set_order = create_signal(["a", "b", "c"])
    wyb["reconciler"].render(ul(lambda: [li(k, key=k) for k in order()]), root_element)
    lst = root_element.element.childNodes[0]
    b_node = _elements(lst)[1]

    set_order(["b", "d"])
    flush()
    items = _elements(lst)
    assert [n.childNodes[0].nodeValue for n in items] == ["b", "d"]
    assert items[0] is b_node


def test_unkeyed_list_patches_by_position(wyb, root_element):
    render = wyb["reconciler"].render
    render(ul(li("a"), li("b")), root_element)
    lst = root_element.element.childNodes[0]
    first, second = _elements(lst)

    render(ul(li("x"), li("y"), li("z")), root_element)
    items = _elements(lst)
    assert [n.childNodes[0].nodeValue for n in items] == ["x", "y", "z"]
    assert items[0] is first and items[1] is second

    render(ul(li("only")), root_element)
    items = _elements(lst)
    assert [n.childNodes[0].nodeValue for n in items] == ["only"]
    assert items[0] is first


def test_fragment_children_are_flattened_into_parent(wyb, root_element):
    wyb["reconciler"].render(div(Fragment(span("a"), span("b")), span("c")), root_element)
    d = root_element.element.childNodes[0]
    assert [n.tag for n in _elements(d)] == ["span", "span", "span"]
    assert _texts(d) == ["a", "b", "c"]


def test_root_fragment_uses_comment_markers(wyb, root_element):
    root = wyb["reconciler"].render(Fragment(p("a"), p("b")), root_element)
    container = root_element.element
    assert [n.tag for n in _elements(container)] == ["p", "p"]
    comments = [n for n in container.childNodes if getattr(n, "_is_comment", False)]
    assert len(comments) == 2
    assert container.childNodes[0] is comments[0]
    assert container.childNodes[-1] is comments[1]
    root.dispose()
    assert container.childNodes == []


# ---------------------------------------------------------------------------
# Refs
# ---------------------------------------------------------------------------


def test_ref_object_is_assigned_and_reset(wyb, root_element):
    dom = wyb["dom"]
    ref = dom.Ref()
    root = wyb["reconciler"].render(div(span("x", ref=ref)), root_element)
    assert isinstance(ref.current, dom.Element)
    target = _elements(root_element.element.childNodes[0])[0]
    assert ref.current.element is target
    assert ref.current.node_id == target._wyb_id
    root.dispose()
    assert ref.current is None


def test_callable_ref_and_ref_list(wyb, root_element):
    dom = wyb["dom"]
    seen = []
    ref = dom.Ref()
    root = wyb["reconciler"].render(div(ref=[ref, seen.append]), root_element)
    d = root_element.element.childNodes[0]
    assert ref.current.element is d
    assert len(seen) == 1 and seen[0].element is d
    root.dispose()
    assert ref.current is None
    assert len(seen) == 1


# ---------------------------------------------------------------------------
# SVG
# ---------------------------------------------------------------------------


def test_svg_subtree_is_namespaced(wyb, root_element):
    tree = div(svg(circle(cx=1, stroke_width=2), view_box="0 0 10 10"))
    wyb["reconciler"].render(tree, root_element)
    d = root_element.element.childNodes[0]
    svg_node = _elements(d)[0]
    circle_node = _elements(svg_node)[0]
    assert getattr(d, "namespaceURI", None) is None
    assert svg_node.namespaceURI == NS_SVG
    assert circle_node.namespaceURI == NS_SVG
    assert svg_node.attributes["viewBox"] == "0 0 10 10"
    assert circle_node.attributes["stroke-width"] == "2"
    # The reconciler records the inferred namespace on the mounted VNodes.
    svg_vnode = tree.children[0]
    assert svg_vnode.ns is None
    assert svg_vnode.children[0].ns == NS_SVG


def test_foreign_object_switches_back_to_html(wyb, root_element):
    wyb["reconciler"].render(svg(foreignObject(div("html"))), root_element)
    svg_node = root_element.element.childNodes[0]
    fo = _elements(svg_node)[0]
    inner = _elements(fo)[0]
    assert fo.namespaceURI == NS_SVG
    assert inner.tag == "div"
    assert getattr(inner, "namespaceURI", None) is None


def test_svg_reactive_attribute(wyb, root_element):
    flush = wyb["reactivity"].flush
    color, set_color = create_signal("red")
    wyb["reconciler"].render(svg(circle(fill=color)), root_element)
    c = _elements(root_element.element.childNodes[0])[0]
    assert c.attributes["fill"] == "red"
    set_color("blue")
    flush()
    assert c.attributes["fill"] == "blue"


# ---------------------------------------------------------------------------
# Template fast path
# ---------------------------------------------------------------------------


def test_static_subtree_mounts_via_template_clone(wyb, root_element, monkeypatch):
    kernel = wyb["kernel"]
    ops = _record_ops(monkeypatch, kernel._backend)
    tree = div(h1("Title"), p("Body", class_="lead"), ul(li("a"), li("b")), id="page")
    wyb["reconciler"].render(tree, root_element)

    codes = [op[0] for op in ops]
    assert kernel.OP_REGISTER_TPL in codes
    assert kernel.OP_CLONE_TPL in codes
    assert kernel.OP_CREATE_ELEMENT not in codes

    d = root_element.element.childNodes[0]
    assert d.attributes["id"] == "page"
    assert [n.tag for n in _elements(d)] == ["h1", "p", "ul"]
    assert _elements(d)[1].attributes["class"] == "lead"
    assert _texts(d) == ["Title", "Body", "a", "b"]
    assert [n.childNodes[0].nodeValue for n in _elements(_elements(d)[2])] == ["a", "b"]


def test_same_shape_shares_one_template(wyb, root_element, monkeypatch):
    kernel = wyb["kernel"]
    ops = _record_ops(monkeypatch, kernel._backend)
    render = wyb["reconciler"].render
    other = wyb["dom"].Element(node=StubNode(tag="div"))
    render(div(h1("One"), p("first")), root_element)
    render(div(h1("Two"), p("second")), other)
    assert len([op for op in ops if op[0] == kernel.OP_REGISTER_TPL]) == 1
    assert len([op for op in ops if op[0] == kernel.OP_CLONE_TPL]) == 2
    assert _texts(root_element.element) == ["One", "first"]
    assert _texts(other.element) == ["Two", "second"]


def test_template_wires_holes_events_and_refs(wyb, root_element):
    dom = wyb["dom"]
    backend = wyb["kernel"]._backend
    count, set_count = create_signal(0)
    ref = dom.Ref()
    clicks = []

    tree = div(h1("Counter"), p(lambda: f"count={count()}"), button("+", on_click=clicks.append, ref=ref))
    wyb["reconciler"].render(tree, root_element)
    d = root_element.element.childNodes[0]
    btn = _elements(d)[2]
    assert ref.current.element is btn
    assert _texts(d) == ["Counter", "count=0", "+"]

    backend.dispatch("click", btn)
    assert len(clicks) == 1
    set_count(5)
    wyb["reactivity"].flush()
    assert _texts(d) == ["Counter", "count=5", "+"]


def test_ineligible_tree_falls_back_to_per_node_mount(wyb, root_element, monkeypatch):
    kernel = wyb["kernel"]
    ops = _record_ops(monkeypatch, kernel._backend)
    # A <div> inside a <p> is rewritten by the HTML parser, so this can't be a template.
    wyb["reconciler"].render(p("intro", div("block")), root_element)
    codes = [op[0] for op in ops]
    assert kernel.OP_CLONE_TPL not in codes
    assert kernel.OP_CREATE_ELEMENT in codes
    para = root_element.element.childNodes[0]
    assert _elements(para)[0].tag == "div"
    assert _texts(para) == ["intro", "block"]


# ---------------------------------------------------------------------------
# Delegated events
# ---------------------------------------------------------------------------


def test_click_handler_receives_dom_event(wyb, root_element):
    events = wyb["events"]
    backend = wyb["kernel"]._backend
    seen = []
    wyb["reconciler"].render(div(button("go", on_click=seen.append)), root_element)
    btn = _elements(root_element.element.childNodes[0])[0]

    backend.dispatch("click", btn)
    assert len(seen) == 1
    e = seen[0]
    assert isinstance(e, events.DomEvent)
    assert e.type == "click"
    assert e.target.element is btn
    assert e.current_target.element is btn
    assert e.key is None
    assert e.button == 0


def test_event_bubbles_from_child_to_parent(wyb, root_element):
    backend = wyb["kernel"]._backend
    order = []
    tree = div(
        button("go", on_click=lambda e: order.append(("child", e.current_target.element.tag))),
        on_click=lambda e: order.append(("parent", e.current_target.element.tag)),
    )
    wyb["reconciler"].render(tree, root_element)
    btn = _elements(root_element.element.childNodes[0])[0]

    backend.dispatch("click", btn)
    assert order == [("child", "button"), ("parent", "div")]


def test_stop_propagation_stops_bubbling(wyb, root_element):
    backend = wyb["kernel"]._backend
    order = []

    def child(e):
        order.append("child")
        e.stop_propagation()

    tree = div(button("go", on_click=child), on_click=lambda e: order.append("parent"))
    wyb["reconciler"].render(tree, root_element)
    btn = _elements(root_element.element.childNodes[0])[0]

    backend.dispatch("click", btn)
    assert order == ["child"]


def test_on_input_reads_target_value_and_checked(wyb, root_element):
    backend = wyb["kernel"]._backend
    values = []
    checks = []
    tree = div(
        input_(on_input=lambda e: values.append(e.target.value)),
        input_(type="checkbox", on_change=lambda e: checks.append(e.target.checked)),
    )
    wyb["reconciler"].render(tree, root_element)
    text_input, checkbox = _elements(root_element.element.childNodes[0])

    text_input.value = "hello"
    backend.dispatch("input", text_input)
    checkbox.checked = True
    backend.dispatch("change", checkbox)
    assert values == ["hello"]
    assert checks == [True]


def test_handler_writes_are_flushed_after_dispatch(wyb, root_element):
    backend = wyb["kernel"]._backend
    count, set_count = create_signal(0)
    tree = div(button("+", on_click=lambda e: set_count(lambda n: n + 1)), p(count))
    wyb["reconciler"].render(tree, root_element)
    d = root_element.element.childNodes[0]
    btn = _elements(d)[0]

    backend.dispatch("click", btn)
    backend.dispatch("click", btn)
    assert count() == 2
    assert _texts(d) == ["+", "2"]


def test_handler_swap_on_rerender(wyb, root_element):
    backend = wyb["kernel"]._backend
    render = wyb["reconciler"].render
    first, second = [], []
    render(button("go", on_click=first.append), root_element)
    btn = root_element.element.childNodes[0]
    backend.dispatch("click", btn)

    render(button("go", on_click=second.append), root_element)
    backend.dispatch("click", btn)
    assert len(first) == 1
    assert len(second) == 1


def test_handler_removed_with_none_or_missing_prop(wyb, root_element):
    backend = wyb["kernel"]._backend
    render = wyb["reconciler"].render
    seen = []
    render(div(button("go", on_click=seen.append)), root_element)
    btn = _elements(root_element.element.childNodes[0])[0]
    backend.dispatch("click", btn)
    assert len(seen) == 1

    render(div(button("go", on_click=None)), root_element)
    backend.dispatch("click", btn)
    assert len(seen) == 1

    render(div(button("go", on_click=seen.append)), root_element)
    backend.dispatch("click", btn)
    assert len(seen) == 2

    render(div(button("go")), root_element)
    backend.dispatch("click", btn)
    assert len(seen) == 2


def test_dispose_disables_handlers(wyb, root_element):
    backend = wyb["kernel"]._backend
    seen = []
    root = wyb["reconciler"].render(button("go", on_click=seen.append), root_element)
    btn = root_element.element.childNodes[0]
    root.dispose()
    backend.dispatch("click", btn)
    assert seen == []


# ---------------------------------------------------------------------------
# Element wrapper
# ---------------------------------------------------------------------------


def test_element_wraps_node_and_registers_id(wyb):
    kernel = wyb["kernel"]
    stub = StubNode(tag="section")
    el = wyb["dom"].Element(node=stub)
    assert el.element is stub
    nid = el.node_id
    assert isinstance(nid, int)
    assert el.node_id == nid
    assert kernel.get_node(nid) is stub
    assert stub._wyb_id == nid


def test_element_from_node_id_materializes_lazily(wyb, root_element):
    dom = wyb["dom"]
    wyb["reconciler"].render(div("x"), root_element)
    stub = root_element.element.childNodes[0]
    el = dom.Element(node_id=stub._wyb_id)
    assert el.node_id == stub._wyb_id
    assert el.element is stub


def test_element_constructor_validation(wyb):
    dom = wyb["dom"]
    created = dom.Element("div")
    assert created.element.tag == "div"
    with pytest.raises(ValueError):
        dom.Element()
    with pytest.raises(ValueError):
        dom.Element(existing=True)


def test_element_attribute_and_class_helpers(wyb):
    stub = StubNode(tag="div")
    el = wyb["dom"].Element(node=stub)
    el.set_attr("title", 5)
    assert el.get_attr("title") == "5"
    assert stub.attributes["title"] == "5"
    el.remove_attr("title")
    assert el.get_attr("title") is None

    el.add_class("a", "b")
    assert el.has_class("a") and el.has_class("b")
    el.remove_class("a")
    assert not el.has_class("a") and el.has_class("b")

    el.set_style({"color": "red"}, display="none")
    assert stub.style._props == {"color": "red", "display": "none"}


def test_element_tree_helpers(wyb):
    dom = wyb["dom"]
    parent_stub = StubNode(tag="div")
    parent = dom.Element(node=parent_stub)
    child = dom.Element("span")
    parent.append(child)
    parent.append("text")
    assert parent_stub.childNodes[0] is child.element
    assert parent_stub.childNodes[1]._is_text
    assert parent_stub.childNodes[1].nodeValue == "text"

    child.remove()
    assert child.element not in parent_stub.childNodes
    child.remove()  # detached: no-op

    child.append_to(parent)
    assert parent_stub.childNodes[-1] is child.element

    child.set_text("hello")
    assert child.element.textContent == "hello"

    ref = dom.Ref()
    child.attach_ref(ref)
    assert ref.current is child
