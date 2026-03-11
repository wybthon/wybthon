"""Tests for forward_ref – ref forwarding for function components."""

import wybthon as _wybthon_pkg  # noqa: F401


def test_forward_ref_renders_normally(wyb, root_element):
    vdom, comp_mod = wyb["vdom"], wyb["component"]

    def _render(props, ref):
        return vdom.h("input", {"type": "text", "value": props.get("value", "")})

    FancyInput = comp_mod.forward_ref(_render)
    vdom.render(vdom.h(FancyInput, {"value": "hello"}), root_element)

    inner = root_element.element.childNodes[0]
    assert inner.tag == "input"


def test_forward_ref_passes_ref(wyb, root_element):
    vdom, hooks, comp_mod = wyb["vdom"], wyb["hooks"], wyb["component"]

    captured_ref = [None]

    def _render(props, ref):
        captured_ref[0] = ref
        return vdom.h("input", {"type": "text"})

    FancyInput = comp_mod.forward_ref(_render)
    my_ref = hooks.HookRef(None)
    vdom.render(vdom.h(FancyInput, {"ref": my_ref}), root_element)

    assert captured_ref[0] is my_ref


def test_forward_ref_none_when_no_ref(wyb, root_element):
    vdom, comp_mod = wyb["vdom"], wyb["component"]

    captured_ref = ["sentinel"]

    def _render(props, ref):
        captured_ref[0] = ref
        return vdom.h("span", {}, "no ref")

    FancySpan = comp_mod.forward_ref(_render)
    vdom.render(vdom.h(FancySpan, {"class": "styled"}), root_element)

    assert captured_ref[0] is None


def test_forward_ref_strips_ref_from_props(wyb, root_element):
    vdom, comp_mod = wyb["vdom"], wyb["component"]

    received_props = [None]

    def _render(props, ref):
        received_props[0] = props
        return vdom.h("div", {}, "child")

    Wrapper = comp_mod.forward_ref(_render)
    vdom.render(vdom.h(Wrapper, {"ref": "some_ref", "name": "test"}), root_element)

    assert "ref" not in received_props[0]
    assert received_props[0]["name"] == "test"


def test_forward_ref_has_marker():
    from wybthon.component import forward_ref

    Comp = forward_ref(lambda props, ref: None)
    assert getattr(Comp, "_wyb_forward_ref", False) is True
