"""Tests for the vnode module (VNode, h, Fragment)."""

from wybthon.vnode import Fragment, VNode, flatten_children, h, normalize_children, to_text_vnode


def test_vnode_creation():
    node = VNode(tag="div")
    assert node.tag == "div"
    assert node.props == {}
    assert node.children == []
    assert node.key is None


def test_to_text_vnode():
    node = to_text_vnode("hello")
    assert node.tag == "_text"
    assert node.props["nodeValue"] == "hello"


def test_to_text_vnode_none():
    node = to_text_vnode(None)
    assert node.props["nodeValue"] == ""


def test_to_text_vnode_number():
    node = to_text_vnode(42)
    assert node.props["nodeValue"] == "42"


def test_flatten_children_basic():
    result = flatten_children(["a", "b", "c"])
    assert result == ["a", "b", "c"]


def test_flatten_children_nested():
    result = flatten_children(["a", ["b", ["c"]], "d"])
    assert result == ["a", "b", "c", "d"]


def test_flatten_children_none():
    result = flatten_children(["a", None, "b"])
    assert result == ["a", "b"]


def test_flatten_children_tuples():
    result = flatten_children(["a", ("b", "c"), "d"])
    assert result == ["a", "b", "c", "d"]


def test_normalize_children():
    result = normalize_children(["hello", VNode(tag="span")])
    assert len(result) == 2
    assert result[0].tag == "_text"
    assert result[0].props["nodeValue"] == "hello"
    assert result[1].tag == "span"


def test_h_element():
    node = h("div", {"class": "test"}, "hello")
    assert node.tag == "div"
    assert node.props["class"] == "test"
    assert len(node.children) == 1
    assert node.children[0] == "hello"


def test_h_with_key():
    node = h("li", {"key": "item-1"}, "text")
    assert node.key == "item-1"


def test_h_component():
    def MyComp(props):
        return VNode(tag="div")

    node = h(MyComp, {"value": 5}, "child")
    assert node.tag is MyComp
    assert node.props["value"] == 5
    assert node.props["children"] == ["child"]
    assert node.children == []


def test_h_component_no_children():
    def MyComp(props):
        return VNode(tag="div")

    node = h(MyComp, {"value": 5})
    assert "children" not in node.props


def test_h_flattens_children():
    node = h("ul", {}, ["a", "b"], "c")
    assert node.children == ["a", "b", "c"]


def test_h_none_children():
    node = h("div", {}, "a", None, "b")
    assert node.children == ["a", "b"]


def test_fragment():
    frag = Fragment("a", "b")
    assert frag.tag == "_fragment"
    assert frag.props == {}
    assert len(frag.children) == 2


def test_fragment_from_props():
    frag = Fragment({"children": ["x", "y"]})
    assert frag.tag == "_fragment"
    assert frag.props == {}
    assert len(frag.children) == 2


def test_normalize_children_flattens_fragments():
    frag = Fragment(VNode(tag="p"), VNode(tag="span"))
    result = normalize_children([VNode(tag="div"), frag, VNode(tag="a")])
    assert [v.tag for v in result] == ["div", "p", "span", "a"]
