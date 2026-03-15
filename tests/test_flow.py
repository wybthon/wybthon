"""Tests for flow control primitives (Show, For, Index, Switch, Match, Dynamic)."""

from wybthon.flow import Dynamic, For, Index, Match, Show, Switch
from wybthon.vnode import h


def test_show_truthy_renders_child_vnode():
    child = h("p", {}, "visible")
    result = Show(True, child)
    assert result.tag == "p"


def test_show_falsy_renders_empty():
    child = h("p", {}, "visible")
    result = Show(False, child)
    assert result.tag == "_text"
    assert result.props["nodeValue"] == ""


def test_show_with_fallback():
    result = Show(False, h("p", {}, "main"), fallback=h("p", {}, "fallback"))
    assert result.tag == "p"
    assert result.children[0] == "fallback"


def test_show_callable_condition():
    result = Show(lambda: True, h("p", {}, "ok"))
    assert result.tag == "p"


def test_show_callable_children():
    result = Show(True, lambda cond: h("p", {}, f"got {cond}"))
    assert result.tag == "p"


def test_for_renders_items():
    items = ["A", "B", "C"]
    result = For(items, lambda item, idx: h("li", {"key": idx()}, item))
    assert result.tag == "span"
    assert len(result.children) == 3


def test_for_empty_list():
    result = For([], lambda item, idx: h("li", {}, item))
    assert result.tag == "_text"


def test_for_callable_each():
    result = For(lambda: [1, 2], lambda item, idx: h("li", {}, str(item)))
    assert result.tag == "span"
    assert len(result.children) == 2


def test_for_index_getter():
    indices = []
    For([10, 20, 30], lambda item, idx: (indices.append(idx()), h("li", {}, str(item)))[-1])
    assert indices == [0, 1, 2]


def test_index_renders_items():
    result = Index([10, 20], lambda item, idx: h("li", {}, str(item())))
    assert result.tag == "span"
    assert len(result.children) == 2


def test_index_empty_list():
    result = Index([], lambda item, idx: h("li", {}, str(item())))
    assert result.tag == "_text"


def test_index_item_getter():
    captured = []
    Index(["a", "b"], lambda item, idx: (captured.append(item()), h("li", {}, item()))[-1])
    assert captured == ["a", "b"]


def test_switch_first_match():
    result = Switch(
        Match(True, h("p", {}, "first")),
        Match(True, h("p", {}, "second")),
        fallback=h("p", {}, "default"),
    )
    assert result.tag == "p"
    assert result.children[0] == "first"


def test_switch_no_match_uses_fallback():
    result = Switch(
        Match(False, h("p", {}, "nope")),
        fallback=h("p", {}, "default"),
    )
    assert result.tag == "p"
    assert result.children[0] == "default"


def test_switch_no_match_no_fallback():
    result = Switch(
        Match(False, h("p", {}, "nope")),
    )
    assert result.tag == "_text"


def test_switch_callable_when():
    result = Switch(
        Match(lambda: True, h("p", {}, "ok")),
    )
    assert result.tag == "p"


def test_dynamic_with_string_tag():
    result = Dynamic("div", {"class": "test"}, children=["hello"])
    assert result.tag == "div"


def test_dynamic_with_component():
    def MyComp(props):
        return h("span", {}, props.get("text", ""))

    result = Dynamic(MyComp, {"text": "hi"})
    assert result.tag is MyComp


def test_dynamic_with_none():
    result = Dynamic(None)
    assert result.tag == "_text"


def test_dynamic_kwargs():
    result = Dynamic("div", children=["content"], id="main")
    assert result.tag == "div"
    assert result.props.get("id") == "main"
