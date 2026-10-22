"""Rendering tests against the in-memory stub DOM via the batched kernel.

Markup is written as `html(t"...")` templates. Tests about the generic
reconciler (patching a re-rendered tree in place, keyed children, VNode
fields) build their trees with `h()`, which always mounts node by node.
"""

import pytest
from conftest import StubNode, collect_texts

from wybthon import html
from wybthon.reactivity import create_signal
from wybthon.vnode import NS_SVG, Fragment, h, hole


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
    wyb["reconciler"].render(html(t'<div id="x">hi</div>'), root_element)
    d = root_element.element.childNodes[0]
    assert d.tag == "div"
    assert d.attributes["id"] == "x"
    assert _texts(d) == ["hi"]


def test_mount_h_element_with_text(wyb, root_element):
    wyb["reconciler"].render(h("div", {"id": "x"}, "hi"), root_element)
    d = root_element.element.childNodes[0]
    assert d.tag == "div"
    assert d.attributes["id"] == "x"
    assert _texts(d) == ["hi"]


@pytest.mark.parametrize("kind", ["template", "h"])
def test_mount_nested_tree(wyb, root_element, kind):
    if kind == "template":
        tree = html(t"<div><span>a</span><p>b<em>c</em></p></div>")
    else:
        tree = h("div", None, h("span", None, "a"), h("p", None, "b", h("em", None, "c")))
    wyb["reconciler"].render(tree, root_element)
    d = root_element.element.childNodes[0]
    assert [n.tag for n in _elements(d)] == ["span", "p"]
    para = _elements(d)[1]
    assert para.childNodes[0].nodeValue == "b"
    assert _elements(para)[0].tag == "em"
    assert _texts(d) == ["a", "b", "c"]


def test_render_returns_root_and_dispose_clears_container(wyb, root_element):
    reconciler = wyb["reconciler"]
    backend = wyb["kernel"]._backend
    root = reconciler.render(html(t"<div>x</div>"), root_element)
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
    root1 = render(h("div", {"title": "t1"}, "a"), root_element)
    d = root_element.element.childNodes[0]
    root2 = render(h("div", {"title": "t2"}, "b"), root_element)
    assert root2 is root1
    assert len(root_element.element.childNodes) == 1
    assert root_element.element.childNodes[0] is d
    assert d.attributes["title"] == "t2"
    assert _texts(d) == ["b"]


def test_render_twice_patches_the_same_template_in_place(wyb, root_element):
    render = wyb["reconciler"].render

    def view(title, body):
        return html(t"<div title={title}>{body}</div>")

    root1 = render(view("t1", "a"), root_element)
    d = root_element.element.childNodes[0]
    root2 = render(view("t2", "b"), root_element)
    assert root2 is root1
    assert root_element.element.childNodes == [d]
    assert d.attributes["title"] == "t2"
    assert _texts(d) == ["b"]


def test_render_accepts_node_id_container(wyb, root_element):
    root = wyb["reconciler"].render(html(t"<div>x</div>"), root_element.node_id)
    assert root.container.element is root_element.element
    assert _texts(root_element.element) == ["x"]


# ---------------------------------------------------------------------------
# Patching text and attributes (generic reconciler: h() trees)
# ---------------------------------------------------------------------------


def test_patch_text_reuses_text_node(wyb, root_element):
    render = wyb["reconciler"].render
    render(h("div", None, "a"), root_element)
    text_node = root_element.element.childNodes[0].childNodes[0]
    render(h("div", None, "b"), root_element)
    assert root_element.element.childNodes[0].childNodes[0] is text_node
    assert text_node.nodeValue == "b"


def test_patch_attribute_add_change_remove(wyb, root_element):
    render = wyb["reconciler"].render
    render(h("div"), root_element)
    d = root_element.element.childNodes[0]
    assert "title" not in d.attributes

    render(h("div", {"title": "a"}), root_element)
    assert d.attributes["title"] == "a"
    render(h("div", {"title": "b"}), root_element)
    assert d.attributes["title"] == "b"
    render(h("div", {"title": None}), root_element)
    assert "title" not in d.attributes
    render(h("div", {"title": "c"}), root_element)
    render(h("div"), root_element)
    assert "title" not in d.attributes


def test_hyphenated_attribute_names(wyb, root_element):
    wyb["reconciler"].render(h("div", {"aria_label": "Close", "data-testid": "root"}), root_element)
    d = root_element.element.childNodes[0]
    assert d.attributes["aria-label"] == "Close"
    assert d.attributes["data-testid"] == "root"


def test_template_attribute_names_are_html_names(wyb, root_element):
    wyb["reconciler"].render(html(t'<label for="name" class="lbl" aria-label="Close">x</label>'), root_element)
    node = root_element.element.childNodes[0]
    assert node.attributes == {"for": "name", "class": "lbl", "aria-label": "Close"}


def test_boolean_attributes(wyb, root_element):
    render = wyb["reconciler"].render
    render(h("button", {"disabled": True, "draggable": True}, "go"), root_element)
    b = root_element.element.childNodes[0]
    assert b.attributes["disabled"] == ""
    assert b.attributes["draggable"] == "true"

    render(h("button", {"disabled": False, "draggable": False}, "go"), root_element)
    assert "disabled" not in b.attributes
    assert "draggable" not in b.attributes


def test_dom_property_props(wyb, root_element):
    render = wyb["reconciler"].render
    render(h("input", {"value": "hi", "checked": True}), root_element)
    inp = root_element.element.childNodes[0]
    assert inp.value == "hi"
    assert inp.checked is True
    assert "value" not in inp.attributes
    assert "checked" not in inp.attributes

    render(h("input", {"value": "yo", "checked": False}), root_element)
    assert inp.value == "yo"
    assert inp.checked is False


def test_template_dom_property_props(wyb, root_element):
    value = "hi"
    wyb["reconciler"].render(html(t"<input value={value} checked={True}>"), root_element)
    inp = root_element.element.childNodes[0]
    assert inp.value == "hi"
    assert inp.checked is True
    assert "value" not in inp.attributes
    assert "checked" not in inp.attributes


# ---------------------------------------------------------------------------
# class / style
# ---------------------------------------------------------------------------


def test_class_as_str_list_dict(wyb, root_element):
    render = wyb["reconciler"].render
    render(h("div", {"class_": "a b"}), root_element)
    d = root_element.element.childNodes[0]
    assert d.attributes["class"] == "a b"

    render(h("div", {"class": ["x", None, "", "y"]}), root_element)
    assert d.attributes["class"] == "x y"

    render(h("div", {"class_": {"on": True, "off": False, "also": 1}}), root_element)
    assert d.attributes["class"] == "on also"

    render(h("div", {"class_": {"off": False}}), root_element)
    assert "class" not in d.attributes


def test_class_dict_with_accessor_values_updates(wyb, root_element):
    flush = wyb["reactivity"].flush
    active, set_active = create_signal(False)
    classes = {"base": True, "active": active}
    wyb["reconciler"].render(html(t"<div class={classes}></div>"), root_element)
    d = root_element.element.childNodes[0]
    assert d.attributes["class"] == "base"

    set_active(True)
    flush()
    assert d.attributes["class"] == "base active"

    set_active(False)
    flush()
    assert d.attributes["class"] == "base"


def test_class_expression_updates(wyb, root_element):
    flush = wyb["reactivity"].flush
    theme, set_theme = create_signal("light")
    wyb["reconciler"].render(html(t"<div class={f'theme-{theme()}'}></div>"), root_element)
    d = root_element.element.childNodes[0]
    assert d.attributes["class"] == "theme-light"
    set_theme("dark")
    flush()
    assert d.attributes["class"] == "theme-dark"


def test_style_dict_snake_camel_and_kebab_keys(wyb, root_element):
    render = wyb["reconciler"].render
    render(h("div", {"style": {"background_color": "red", "fontSize": "12px", "margin-top": "1px"}}), root_element)
    d = root_element.element.childNodes[0]
    assert d.style._props == {"background-color": "red", "font-size": "12px", "margin-top": "1px"}

    render(h("div", {"style": {"background_color": "blue"}}), root_element)
    assert d.style._props == {"background-color": "blue"}


def test_style_string(wyb, root_element):
    wyb["reconciler"].render(html(t'<div style="color: red"></div>'), root_element)
    d = root_element.element.childNodes[0]
    assert d.attributes["style"] == "color: red"


def test_style_dict_with_accessor_values_updates(wyb, root_element):
    flush = wyb["reactivity"].flush
    color, set_color = create_signal("red")
    styles = {"color": color, "display": "block"}
    wyb["reconciler"].render(html(t"<div style={styles}></div>"), root_element)
    d = root_element.element.childNodes[0]
    assert d.style._props == {"color": "red", "display": "block"}
    set_color("blue")
    flush()
    assert d.style._props == {"color": "blue", "display": "block"}


# ---------------------------------------------------------------------------
# Reactive props
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("kind", ["template", "h"])
def test_reactive_attribute_updates_on_signal_write(wyb, root_element, kind):
    flush = wyb["reactivity"].flush
    title, set_title = create_signal("one")
    tree = html(t"<div title={title}></div>") if kind == "template" else h("div", {"title": title})
    wyb["reconciler"].render(tree, root_element)
    d = root_element.element.childNodes[0]
    assert d.attributes["title"] == "one"
    set_title("two")
    flush()
    assert d.attributes["title"] == "two"


def test_reactive_boolean_attribute(wyb, root_element):
    flush = wyb["reactivity"].flush
    count, set_count = create_signal(0)
    wyb["reconciler"].render(html(t"<button disabled={count() >= 1}>go</button>"), root_element)
    b = root_element.element.childNodes[0]
    assert "disabled" not in b.attributes
    set_count(1)
    flush()
    assert b.attributes["disabled"] == ""
    set_count(0)
    flush()
    assert "disabled" not in b.attributes


@pytest.mark.parametrize("kind", ["template", "h"])
def test_reactive_props_update_independently(wyb, root_element, monkeypatch, kind):
    kernel = wyb["kernel"]
    flush = wyb["reactivity"].flush
    title, set_title = create_signal("t1")
    ident, _set_ident = create_signal("i1")
    tree = (
        html(t"<div title={title} id={ident}></div>") if kind == "template" else h("div", {"title": title, "id": ident})
    )
    wyb["reconciler"].render(tree, root_element)
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
    wyb["reconciler"].render(html(t"<input value={value()}>"), root_element)
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
    wyb["reconciler"].render(html(t"<div>{f'n={count()}'}</div>"), root_element)
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
    wyb["reconciler"].render(html(t"<div>{content}</div>"), root_element)
    d = root_element.element.childNodes[0]
    assert _texts(d) == ["text"]
    assert _elements(d) == []

    set_content(html(t"<span>el</span>"))
    flush()
    assert [n.tag for n in _elements(d)] == ["span"]
    assert _texts(d) == ["el"]

    set_content(["a", h("span", None, "b"), None])
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
    wyb["reconciler"].render(h("p", None, hole(lambda: f"Hi {name()}", key="greet")), root_element)
    para = root_element.element.childNodes[0]
    assert _texts(para) == ["Hi Ada"]
    set_name("Bob")
    flush()
    assert _texts(para) == ["Hi Bob"]


@pytest.mark.parametrize("kind", ["template", "h"])
def test_hole_children_inside_static_siblings_keep_order(wyb, root_element, kind):
    flush = wyb["reactivity"].flush
    mid, set_mid = create_signal("m1")
    if kind == "template":
        tree = html(t"<div><span>first</span>{mid}<span>last</span></div>")
    else:
        tree = h("div", None, h("span", None, "first"), mid, h("span", None, "last"))
    wyb["reconciler"].render(tree, root_element)
    d = root_element.element.childNodes[0]
    assert _texts(d) == ["first", "m1", "last"]
    set_mid("m2")
    flush()
    assert _texts(d) == ["first", "m2", "last"]


# ---------------------------------------------------------------------------
# Lists and fragments
# ---------------------------------------------------------------------------


def _keyed_items(order):
    return h("ul", None, lambda: [h("li", {"key": k}, k) for k in order()])


def test_keyed_list_reorder_moves_nodes(wyb, root_element):
    flush = wyb["reactivity"].flush
    order, set_order = create_signal(["a", "b", "c"])
    wyb["reconciler"].render(_keyed_items(order), root_element)
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
    wyb["reconciler"].render(_keyed_items(order), root_element)
    lst = root_element.element.childNodes[0]
    b_node = _elements(lst)[1]

    set_order(["b", "d"])
    flush()
    items = _elements(lst)
    assert [n.childNodes[0].nodeValue for n in items] == ["b", "d"]
    assert items[0] is b_node


def test_unkeyed_list_patches_by_position(wyb, root_element):
    render = wyb["reconciler"].render

    def items(*labels):
        return h("ul", None, [h("li", None, label) for label in labels])

    render(items("a", "b"), root_element)
    lst = root_element.element.childNodes[0]
    first, second = _elements(lst)

    render(items("x", "y", "z"), root_element)
    nodes = _elements(lst)
    assert [n.childNodes[0].nodeValue for n in nodes] == ["x", "y", "z"]
    assert nodes[0] is first and nodes[1] is second

    render(items("only"), root_element)
    nodes = _elements(lst)
    assert [n.childNodes[0].nodeValue for n in nodes] == ["only"]
    assert nodes[0] is first


def test_fragment_children_are_flattened_into_parent(wyb, root_element):
    tree = h("div", None, Fragment(h("span", None, "a"), h("span", None, "b")), h("span", None, "c"))
    wyb["reconciler"].render(tree, root_element)
    d = root_element.element.childNodes[0]
    assert [n.tag for n in _elements(d)] == ["span", "span", "span"]
    assert _texts(d) == ["a", "b", "c"]


def test_multi_root_template_is_a_fragment(wyb, root_element):
    wyb["reconciler"].render(html(t"<div>{html(t'<span>a</span><span>b</span>')}<span>c</span></div>"), root_element)
    d = root_element.element.childNodes[0]
    assert [n.tag for n in _elements(d)] == ["span", "span", "span"]
    assert _texts(d) == ["a", "b", "c"]


def test_root_fragment_uses_comment_markers(wyb, root_element):
    root = wyb["reconciler"].render(Fragment(html(t"<p>a</p>"), h("p", None, "b")), root_element)
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
    root = wyb["reconciler"].render(html(t"<div><span ref={ref}>x</span></div>"), root_element)
    assert isinstance(ref.current, dom.Element)
    target = _elements(root_element.element.childNodes[0])[0]
    assert ref.current.element is target
    assert ref.current.node_id == target._wyb_id
    root.dispose()
    assert ref.current is None


@pytest.mark.parametrize("kind", ["template", "h"])
def test_callable_ref_and_ref_list(wyb, root_element, kind):
    dom = wyb["dom"]
    seen = []
    ref = dom.Ref()
    refs = [ref, seen.append]
    tree = html(t"<div ref={refs}></div>") if kind == "template" else h("div", {"ref": refs})
    root = wyb["reconciler"].render(tree, root_element)
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
    tree = h("div", None, h("svg", {"viewBox": "0 0 10 10"}, h("circle", {"cx": 1, "stroke_width": 2})))
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


def test_template_svg_subtree_is_namespaced(wyb, root_element):
    tree = html(t'<div><svg viewBox="0 0 10 10"><circle cx="1" stroke-width="2"></circle></svg></div>')
    wyb["reconciler"].render(tree, root_element)
    d = root_element.element.childNodes[0]
    svg_node = _elements(d)[0]
    circle_node = _elements(svg_node)[0]
    assert getattr(d, "namespaceURI", None) is None
    assert svg_node.namespaceURI == NS_SVG
    assert circle_node.namespaceURI == NS_SVG
    assert svg_node.attributes["viewBox"] == "0 0 10 10"
    assert circle_node.attributes["stroke-width"] == "2"


@pytest.mark.parametrize("kind", ["template", "h"])
def test_foreign_object_switches_back_to_html(wyb, root_element, kind):
    if kind == "template":
        tree = html(t"<svg><foreignObject><div>html</div></foreignObject></svg>")
    else:
        tree = h("svg", None, h("foreignObject", None, h("div", None, "html")))
    wyb["reconciler"].render(tree, root_element)
    svg_node = root_element.element.childNodes[0]
    fo = _elements(svg_node)[0]
    inner = _elements(fo)[0]
    assert fo.namespaceURI == NS_SVG
    assert inner.tag == "div"
    assert getattr(inner, "namespaceURI", None) is None


def test_svg_reactive_attribute(wyb, root_element):
    flush = wyb["reactivity"].flush
    color, set_color = create_signal("red")
    wyb["reconciler"].render(html(t"<svg><circle fill={color()}></circle></svg>"), root_element)
    c = _elements(root_element.element.childNodes[0])[0]
    assert c.attributes["fill"] == "red"
    set_color("blue")
    flush()
    assert c.attributes["fill"] == "blue"


# ---------------------------------------------------------------------------
# Template fast path
# ---------------------------------------------------------------------------


def test_template_mounts_via_one_clone(wyb, root_element, monkeypatch):
    kernel = wyb["kernel"]
    ops = _record_ops(monkeypatch, kernel._backend)
    tree = html(t'<div id="page"><h1>Title</h1><p class="lead">Body</p><ul><li>a</li><li>b</li></ul></div>')
    wyb["reconciler"].render(tree, root_element)

    codes = [op[0] for op in ops]
    assert kernel.OP_REGISTER_TPL in codes
    assert codes.count(kernel.OP_CLONE) == 1
    assert kernel.OP_CREATE_ELEMENT not in codes

    d = root_element.element.childNodes[0]
    assert d.attributes["id"] == "page"
    assert [n.tag for n in _elements(d)] == ["h1", "p", "ul"]
    assert _elements(d)[1].attributes["class"] == "lead"
    assert _texts(d) == ["Title", "Body", "a", "b"]
    assert [n.childNodes[0].nodeValue for n in _elements(_elements(d)[2])] == ["a", "b"]


def test_one_literal_shares_one_template(wyb, root_element, monkeypatch):
    kernel = wyb["kernel"]
    ops = _record_ops(monkeypatch, kernel._backend)
    render = wyb["reconciler"].render
    other = wyb["dom"].Element(node=StubNode(tag="div"))

    def view(title, body):
        return html(t"<div><h1>{title}</h1><p>{body}</p></div>")

    render(view("One", "first"), root_element)
    render(view("Two", "second"), other)
    assert len([op for op in ops if op[0] == kernel.OP_REGISTER_TPL]) == 1
    assert len([op for op in ops if op[0] == kernel.OP_CLONE]) == 2
    assert _texts(root_element.element) == ["One", "first"]
    assert _texts(other.element) == ["Two", "second"]


def test_template_wires_holes_events_and_refs(wyb, root_element):
    dom = wyb["dom"]
    backend = wyb["kernel"]._backend
    count, set_count = create_signal(0)
    ref = dom.Ref()
    clicks = []

    tree = html(
        t"<div><h1>Counter</h1><p>{f'count={count()}'}</p><button onclick={clicks.append} ref={ref}>+</button></div>"
    )
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


def test_h_trees_mount_per_node(wyb, root_element, monkeypatch):
    kernel = wyb["kernel"]
    ops = _record_ops(monkeypatch, kernel._backend)
    # h() is the programmatic layer: its trees mount node by node, without templates.
    wyb["reconciler"].render(h("p", None, "intro", h("span", None, "inline")), root_element)
    codes = [op[0] for op in ops]
    assert kernel.OP_REGISTER_TPL not in codes
    assert kernel.OP_CLONE not in codes
    assert [op[2] for op in ops if op[0] == kernel.OP_CREATE_ELEMENT] == ["p", "span"]
    para = root_element.element.childNodes[0]
    assert _elements(para)[0].tag == "span"
    assert _texts(para) == ["intro", "inline"]


# ---------------------------------------------------------------------------
# Delegated events
# ---------------------------------------------------------------------------


def test_click_handler_receives_dom_event(wyb, root_element):
    events = wyb["events"]
    backend = wyb["kernel"]._backend
    seen = []
    wyb["reconciler"].render(html(t"<div><button onclick={seen.append}>go</button></div>"), root_element)
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

    def child(e):
        order.append(("child", e.current_target.element.tag))

    def parent(e):
        order.append(("parent", e.current_target.element.tag))

    wyb["reconciler"].render(html(t"<div onclick={parent}><button onclick={child}>go</button></div>"), root_element)
    btn = _elements(root_element.element.childNodes[0])[0]

    backend.dispatch("click", btn)
    assert order == [("child", "button"), ("parent", "div")]


def test_stop_propagation_stops_bubbling(wyb, root_element):
    backend = wyb["kernel"]._backend
    order = []

    def child(e):
        order.append("child")
        e.stop_propagation()

    def parent(e):
        order.append("parent")

    wyb["reconciler"].render(html(t"<div onclick={parent}><button onclick={child}>go</button></div>"), root_element)
    btn = _elements(root_element.element.childNodes[0])[0]

    backend.dispatch("click", btn)
    assert order == ["child"]


def test_on_input_reads_target_value_and_checked(wyb, root_element):
    backend = wyb["kernel"]._backend
    values = []
    checks = []

    def on_input(e):
        values.append(e.target.value)

    def on_change(e):
        checks.append(e.target.checked)

    tree = html(t'<div><input oninput={on_input}><input type="checkbox" onchange={on_change}></div>')
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

    def increment():
        set_count(lambda n: n + 1)

    wyb["reconciler"].render(html(t"<div><button onclick={increment}>+</button><p>{count}</p></div>"), root_element)
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
    render(h("button", {"on_click": first.append}, "go"), root_element)
    btn = root_element.element.childNodes[0]
    backend.dispatch("click", btn)

    render(h("button", {"on_click": second.append}, "go"), root_element)
    backend.dispatch("click", btn)
    assert len(first) == 1
    assert len(second) == 1


def test_handler_removed_with_none_or_missing_prop(wyb, root_element):
    backend = wyb["kernel"]._backend
    render = wyb["reconciler"].render
    seen = []

    def view(props):
        return h("div", None, h("button", props, "go"))

    render(view({"on_click": seen.append}), root_element)
    btn = _elements(root_element.element.childNodes[0])[0]
    backend.dispatch("click", btn)
    assert len(seen) == 1

    render(view({"on_click": None}), root_element)
    backend.dispatch("click", btn)
    assert len(seen) == 1

    render(view({"onClick": seen.append}), root_element)
    backend.dispatch("click", btn)
    assert len(seen) == 2

    render(view({}), root_element)
    backend.dispatch("click", btn)
    assert len(seen) == 2


def test_dispose_disables_handlers(wyb, root_element):
    backend = wyb["kernel"]._backend
    seen = []
    root = wyb["reconciler"].render(html(t"<button onclick={seen.append}>go</button>"), root_element)
    btn = root_element.element.childNodes[0]
    root.dispose()
    backend.dispatch("click", btn)
    assert seen == []


def test_zero_arg_handlers_are_called_without_the_event(wyb, root_element):
    backend = wyb["kernel"]._backend
    count, set_count = create_signal(0)
    calls = []

    class Model:
        def ping(self):
            calls.append("method")

    model = Model()

    def increment():
        set_count(lambda n: n + 1)

    def with_event(e):
        calls.append(e.type)

    def defaulted(e=None):
        calls.append(e is not None)

    tree = html(t"""
      <div>
        <button onclick={increment}>+</button>
        <button onclick={model.ping}>m</button>
        <button onclick={with_event}>e</button>
        <button onclick={defaulted}>d</button>
        <p>{count}</p>
      </div>
    """)
    wyb["reconciler"].render(tree, root_element)
    plus, method, with_event_button, defaulted_button = _elements(root_element.element.childNodes[0])[:4]
    backend.dispatch("click", plus)
    backend.dispatch("click", plus)
    backend.dispatch("click", method)
    backend.dispatch("click", with_event_button)
    backend.dispatch("click", defaulted_button)
    assert count() == 2
    assert [t for t in _texts(root_element.element.childNodes[0]) if t.strip()][-1] == "2"
    assert calls == ["method", "click", True]


def test_zero_arg_handler_swap_and_bubbling(wyb, root_element):
    backend = wyb["kernel"]._backend
    render = wyb["reconciler"].render
    order = []
    render(
        h(
            "div",
            {"on_click": lambda: order.append("parent")},
            h("button", {"on_click": lambda: order.append("child")}, "go"),
        ),
        root_element,
    )
    btn = _elements(root_element.element.childNodes[0])[0]
    backend.dispatch("click", btn)
    render(h("div", None, h("button", {"on_click": lambda: order.append("child2")}, "go")), root_element)
    backend.dispatch("click", btn)
    assert order == ["child", "parent", "child2"]


# ---------------------------------------------------------------------------
# Template interpolations
# ---------------------------------------------------------------------------


def test_static_interpolations_render_their_values(wyb, root_element):
    name = "Ada"
    n = 3
    wyb["reconciler"].render(html(t"<p>Hello {name}, you have {n} items</p>"), root_element)
    para = root_element.element.childNodes[0]
    assert "".join(_texts(para)) == "Hello Ada, you have 3 items"


def test_reactive_interpolations_update_independently(wyb, root_element):
    flush = wyb["reactivity"].flush
    count, set_count = create_signal(1)
    label = "Count"
    renders = []

    def doubled():
        renders.append(1)
        return count() * 2

    wyb["reconciler"].render(html(t"<p>{label}: {count} (doubled: {doubled})</p>"), root_element)
    para = root_element.element.childNodes[0]
    assert "".join(_texts(para)) == "Count: 1 (doubled: 2)"
    set_count(5)
    flush()
    assert "".join(_texts(para)) == "Count: 5 (doubled: 10)"
    assert len(renders) == 2


def test_interpolation_format_specs_and_conversions(wyb, root_element):
    flush = wyb["reactivity"].flush
    price, set_price = create_signal(3.14159)
    word = "hi"
    nothing = None
    wyb["reconciler"].render(
        html(t"<div><p>${price():.2f}</p><p>{word!r} {word:>4}|{nothing}|</p><p>{12:04d}</p></div>"), root_element
    )
    paras = _elements(root_element.element.childNodes[0])
    assert ["".join(_texts(x)) for x in paras] == ["$3.14", "'hi'   hi||", "0012"]
    set_price(2)
    flush()
    assert "".join(_texts(paras[0])) == "$2.00"


def test_interpolating_markup_expands_into_children(wyb, root_element):
    flush = wyb["reactivity"].flush
    name, set_name = create_signal("Ada")
    there = html(t"<strong>there</strong>")
    emphasis = [html(t"<em>a</em>"), html(t"<em>b</em>")]
    wyb["reconciler"].render(html(t"<p>Hi {there}, {name}! {emphasis}</p>"), root_element)
    para = root_element.element.childNodes[0]
    assert [n.tag for n in _elements(para)] == ["strong", "em", "em"]
    assert "".join(_texts(para)) == "Hi there, Ada! ab"
    set_name("Grace")
    flush()
    assert "".join(_texts(para)) == "Hi there, Grace! ab"


def test_attribute_parts_static_and_reactive(wyb, root_element):
    flush = wyb["reactivity"].flush
    variant, set_variant = create_signal("primary")
    user_id = 42
    width = 0.5
    view = html(t"""
      <div>
        <a href="/users/{user_id}">Profile</a>
        <div class="card card-{variant()}" style="width: {width:.0%}"></div>
      </div>
    """)
    wyb["reconciler"].render(view, root_element)
    link, card = _elements(root_element.element.childNodes[0])
    assert link.attributes["href"] == "/users/42"
    assert card.attributes["class"] == "card card-primary"
    assert card.attributes["style"] == "width: 50%"
    set_variant("danger")
    flush()
    assert card.attributes["class"] == "card card-danger"
    assert link.attributes["href"] == "/users/42"


def test_template_renders_through_per_node_mount(wyb, root_element):
    flush = wyb["reactivity"].flush
    wyb["kernel"].html_templates = False
    page, set_page = create_signal(1)
    wyb["reconciler"].render(html(t"""<a href="/p/{page()}" title="static {"x"}">Page {page()}</a>"""), root_element)
    link = root_element.element.childNodes[0]
    assert link.attributes == {"href": "/p/1", "title": "static x"}
    assert "".join(_texts(link)) == "Page 1"
    set_page(2)
    flush()
    assert link.attributes["href"] == "/p/2"
    assert "".join(_texts(link)) == "Page 2"


# ---------------------------------------------------------------------------
# Kernel protocol: template-declared listeners and native teardown
# ---------------------------------------------------------------------------


def test_template_handlers_send_no_listen_ops(wyb, root_element, monkeypatch):
    kernel = wyb["kernel"]
    backend = kernel._backend
    ops = _record_ops(monkeypatch, backend)
    clicks = []

    def on_a():
        clicks.append("a")

    def on_b(e):
        clicks.append("b")

    tree = html(t"<div><button onclick={on_a}>a</button><button oninput={on_b}>b</button></div>")
    wyb["reconciler"].render(tree, root_element)
    codes = [op[0] for op in ops]
    assert kernel.OP_CLONE in codes
    assert kernel.OP_LISTEN not in codes
    register = [op for op in ops if op[0] == kernel.OP_REGISTER_TPL][0]
    assert sorted(event for _offset, event in register[5]) == ["click", "input"]
    first = _elements(root_element.element.childNodes[0])[0]
    backend.dispatch("click", first)
    assert clicks == ["a"]


def test_fused_clone_carries_texts_and_anchor(wyb, root_element, monkeypatch):
    kernel = wyb["kernel"]
    ops = _record_ops(monkeypatch, kernel._backend)
    title, body = "Title", "Body"
    wyb["reconciler"].render(html(t"<div><h1>{title}</h1><p>{body}</p></div>"), root_element)
    clones = [op for op in ops if op[0] == kernel.OP_CLONE]
    assert len(clones) == 1
    _code, _first_id, _tpl_id, parent_id, anchor_id, *texts = clones[0]
    assert parent_id == root_element.node_id
    assert texts == ["Title", "Body"]
    assert kernel.OP_INSERT not in [op[0] for op in ops]
    assert kernel.OP_SET_TEXT not in [op[0] for op in ops]
    assert _texts(root_element.element) == ["Title", "Body"]


def test_unmount_disposes_natively_without_release_lists(wyb, root_element, monkeypatch):
    kernel = wyb["kernel"]
    flush = wyb["reactivity"].flush
    show, set_show = create_signal(True)

    def noop():
        pass

    def view():
        return html(t"<div><h1>A</h1><p>B</p><button onclick={noop}>x</button></div>") if show() else None

    wyb["reconciler"].render(html(t"<div>{view}</div>"), root_element)
    ops = _record_ops(monkeypatch, kernel._backend)
    set_show(False)
    flush()
    codes = [op[0] for op in ops]
    assert kernel.OP_RELEASE not in codes
    assert kernel.OP_UNLISTEN not in codes
    assert kernel.OP_DISPOSE in codes or kernel.OP_DISPOSE_RANGE in codes
    assert [t for t in _texts(root_element.element) if t.strip()] == []


def test_template_mount_assigns_el_to_its_root(wyb, root_element):
    tree = html(t"<div><h1>Title</h1><p>Body</p></div>")
    wyb["reconciler"].render(tree, root_element)
    assert tree.el is not None
    assert tree.el == root_element.element.childNodes[0]._wyb_id


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
    wyb["reconciler"].render(html(t"<div>x</div>"), root_element)
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
