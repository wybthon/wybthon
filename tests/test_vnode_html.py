"""Pure VDOM construction tests: `h`, `Fragment`, `hole`, child normalization, and prop names.

Nothing here renders, so no browser stubs are needed.
"""

import importlib

import pytest

from wybthon._dom_props import attr_name, to_kebab
from wybthon.reactivity import create_memo, create_signal
from wybthon.vnode import (
    NS_SVG,
    Fragment,
    VNode,
    flatten_children,
    h,
    hole,
    is_accessor,
    normalize_children,
    to_text_vnode,
)

# ---------------------------------------------------------------------------
# h() / VNode shape
# ---------------------------------------------------------------------------


def test_h_builds_element_vnode_shape():
    handler = lambda e: None  # noqa: E731
    v = h("div", {"id": "x", "on_click": handler}, "a", "b")
    assert isinstance(v, VNode)
    assert v.tag == "div"
    assert v.props == {"id": "x", "on_click": handler}
    assert v.children == ["a", "b"]
    assert v.key is None
    assert v.el is None
    assert v.ns is None


def test_h_none_props_becomes_empty_dict_and_key_is_lifted():
    assert h("div", None).props == {}
    keyed = h("li", {"key": 7}, "seven")
    assert keyed.key == 7
    assert keyed.props["key"] == 7


def test_h_flattens_nested_children_and_drops_none():
    v = h("ul", {}, None, "a", ["b", None, ("c", ["d"])], 5)
    assert v.children == ["a", "b", "c", "d", 5]


def test_h_with_callable_tag_moves_children_into_props():
    def Comp(props):
        return None

    v = h(Comp, {"name": "x"}, "child", ["more"])
    assert v.tag is Comp
    assert v.children == []
    assert v.props["children"] == ["child", "more"]
    assert v.props["name"] == "x"


def test_h_with_callable_tag_keeps_explicit_children_prop():
    def Comp(props):
        return None

    v = h(Comp, {"children": ["explicit"]}, "positional")
    assert v.props["children"] == ["explicit"]


def test_h_with_fragment_tag_makes_fragment_vnode():
    v = h(Fragment, {"key": "k"}, "a", ["b"])
    assert v.tag == "_fragment"
    assert v.children == ["a", "b"]
    assert v.key == "k"
    assert v.props == {}


def test_fragment_helper():
    v = Fragment("a", None, ["b", ["c"]])
    assert v.tag == "_fragment"
    assert v.props == {}
    assert v.children == ["a", "b", "c"]
    assert v.key is None


def test_hole_creates_hole_vnode_with_getter_and_key():
    getter = lambda: "x"  # noqa: E731
    v = hole(getter)
    assert v.tag == "_hole"
    assert v.props["getter"] is getter
    assert v.children == []
    assert v.key is None
    assert hole(getter, key="row").key == "row"


def test_to_text_vnode():
    t = to_text_vnode(42)
    assert t.tag == "_text"
    assert t.props == {"nodeValue": "42"}
    assert t.children == []
    assert to_text_vnode(None).props["nodeValue"] == ""
    assert to_text_vnode(2.5).props["nodeValue"] == "2.5"


# ---------------------------------------------------------------------------
# Child normalization
# ---------------------------------------------------------------------------


def test_flatten_children_recurses_lists_and_tuples():
    assert flatten_children([None, 1, [2, (3, [4, None])], "s"]) == [1, 2, 3, 4, "s"]


def test_normalize_children_coerces_scalars_to_text():
    out = normalize_children([1, 2.5, "s"])
    assert [n.tag for n in out] == ["_text", "_text", "_text"]
    assert [n.props["nodeValue"] for n in out] == ["1", "2.5", "s"]


def test_normalize_children_keeps_vnodes_and_flattens_fragments():
    inner = h("span", None, "in")
    out = normalize_children([h("div", None, "a"), Fragment(inner, Fragment("deep")), "t"])
    assert out[0].tag == "div"
    assert out[1] is inner
    assert out[2].tag == "_text" and out[2].props["nodeValue"] == "deep"
    assert out[3].tag == "_text" and out[3].props["nodeValue"] == "t"


def test_normalize_children_wraps_reactive_expressions_in_holes():
    count, _set_count = create_signal(0)
    memo = create_memo(lambda: count() * 2)
    fn = lambda: "x"  # noqa: E731
    out = normalize_children([count, memo, fn])
    assert [n.tag for n in out] == ["_hole", "_hole", "_hole"]
    assert out[0].props["getter"] is count
    assert out[1].props["getter"] is memo
    assert out[2].props["getter"] is fn


def test_normalize_children_keeps_existing_hole():
    hv = hole(lambda: "x", key="k")
    out = normalize_children([hv])
    assert out == [hv]


def test_normalize_children_skips_none_and_booleans():
    # `cond and Widget()` yields False when the condition fails; like SolidJS,
    # that renders nothing.
    assert normalize_children([True, False, None]) == []


def test_is_accessor():
    count, set_count = create_signal(0)

    class Thing:
        def read(self):
            return 1

        def read_arg(self, x):
            return x

    assert is_accessor(count) is True
    assert is_accessor(create_memo(lambda: 1)) is True
    assert is_accessor(lambda: 1) is True
    assert is_accessor(lambda x=1: x) is True
    assert is_accessor(Thing().read) is True
    assert is_accessor(lambda x: x) is False
    assert is_accessor(Thing().read_arg) is False
    assert is_accessor(set_count) is False
    assert is_accessor("text") is False
    assert is_accessor(42) is False
    assert is_accessor(Thing) is False
    assert is_accessor(None) is False


# ---------------------------------------------------------------------------
# Prop names
# ---------------------------------------------------------------------------


def test_reserved_word_props_are_mapped_when_applied():
    # h() keeps the Python spelling; the prop applier maps it to the attribute.
    assert h("div", {"class_": "card"}).props == {"class_": "card"}
    assert h("label", {"html_for": "name", "class_": "lbl"}).props == {"html_for": "name", "class_": "lbl"}
    assert attr_name("class_") == "class"
    assert attr_name("html_for") == "for"


def test_hyphenated_attribute_names_are_resolved_by_attr_name():
    v = h("div", {"aria_label": "Close", "data_testid": "root"})
    # h() leaves these alone; the prop applier converts them when writing attributes.
    assert v.props == {"aria_label": "Close", "data_testid": "root"}
    assert attr_name("aria_label") == "aria-label"
    assert attr_name("data_testid") == "data-testid"
    assert attr_name("stroke_width") == "stroke-width"
    assert attr_name("class_") == "class"
    assert attr_name("html_for") == "for"
    assert attr_name("for_") == "for"
    assert attr_name("tabindex") == "tabindex"
    assert attr_name("viewBox") == "viewBox"
    # HTML names pass through unchanged.
    assert attr_name("aria-label") == "aria-label"
    assert attr_name("class") == "class"


def test_to_kebab_handles_snake_and_camel():
    assert to_kebab("background_color") == "background-color"
    assert to_kebab("fontSize") == "font-size"
    assert to_kebab("font-size") == "font-size"
    assert to_kebab("color") == "color"


def test_h_builds_custom_element_tags():
    v = h("x-foo", {"size": "large", "class_": "c"}, "hi")
    assert v.tag == "x-foo"
    assert v.children == ["hi"]
    assert v.props == {"size": "large", "class_": "c"}


def test_event_handler_props_pass_through():
    def on_click(e):
        pass

    v = h("a", {"href": "/x", "on_click": on_click}, "link")
    assert v.props["on_click"] is on_click
    assert v.props["href"] == "/x"
    assert h("li", None, "row").key is None


# ---------------------------------------------------------------------------
# Item syntax and t-strings
# ---------------------------------------------------------------------------


def test_element_item_syntax_sets_children_and_returns_the_node():
    v = h("div", {"id": "x"})
    same = v[h("span", None, "a"), "b", None, [h("span", None, "c")]]
    assert same is v
    assert [c if isinstance(c, str) else c.tag for c in v.children] == ["span", "b", "span"]
    assert v.props == {"id": "x"}
    assert h("div")["only"].children == ["only"]


def test_component_item_syntax_sets_children_prop():
    def Comp(props):
        return None

    v = h(Comp, {"title": "T"})["a", h("span", None, "b")]
    assert v.children == []
    assert v.props["children"][0] == "a"
    assert v.props["children"][1].tag == "span"


def test_t_string_children_outside_html_are_rejected():
    name = "Ada"
    with pytest.raises(TypeError, match="html"):
        h("div", None, "a", t"Hello {name}!")
    with pytest.raises(TypeError, match="html"):
        h("div")[t"Hello {name}!"]
    with pytest.raises(TypeError, match="html"):
        Fragment(t"Hello {name}!")


# ---------------------------------------------------------------------------
# SVG
# ---------------------------------------------------------------------------


def test_svg_namespace_is_inferred_at_mount_not_construction():
    v = h("svg", {"viewBox": "0 0 10 10"}, h("circle", {"r": 1}))
    assert v.ns is None
    assert v.children[0].ns is None
    assert NS_SVG == "http://www.w3.org/2000/svg"


# ---------------------------------------------------------------------------
# Removed APIs
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("module", ["wybthon.elements", "wybthon.svg", "wybthon._shapes"])
def test_element_helper_modules_are_gone(module):
    with pytest.raises(ImportError):
        importlib.import_module(module)


def test_element_helpers_are_not_exported():
    import wybthon
    import wybthon.vnode

    for name in ("div", "p", "span", "button", "input_", "element"):
        assert not hasattr(wybthon, name), name
    for name in ("render_template", "template_getter"):
        assert not hasattr(wybthon.vnode, name), name
