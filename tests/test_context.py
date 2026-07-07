import wybthon.reactivity as _rx
from wybthon.context import create_context, use_context
from wybthon.reactivity import Owner


def test_context_via_ownership_tree():
    """Context values are found by walking up the ownership tree."""
    Theme = create_context("light")
    assert use_context(Theme) == "light"

    parent = Owner()
    parent._set_context(Theme.id, "dark")

    child = Owner()
    parent._add_child(child)

    prev = _rx._current_owner
    _rx._current_owner = child
    try:
        assert use_context(Theme) == "dark"

        grandchild = Owner()
        child._add_child(grandchild)
        _rx._current_owner = grandchild
        assert use_context(Theme) == "dark"

        child._set_context(Theme.id, "contrast")
        assert use_context(Theme) == "contrast"
    finally:
        _rx._current_owner = prev


def test_context_provider_method_builds_provider_vnode():
    """``ctx.Provider(value=..., children=...)`` is shorthand for h(Provider, ...)."""
    from wybthon.context import Provider
    from wybthon.vnode import VNode, h

    Theme = create_context("light")
    child = h("p", {}, "content")
    vnode = Theme.Provider(value="dark", children=[child])

    assert isinstance(vnode, VNode)
    assert vnode.tag is Provider
    assert vnode.props["context"] is Theme
    assert vnode.props["value"] == "dark"
    assert vnode.props["children"] == [child]


def test_context_provider_method_normalizes_single_child():
    from wybthon.vnode import h

    Theme = create_context("light")
    child = h("p", {}, "x")
    vnode = Theme.Provider(value="v", children=child)
    assert vnode.props["children"] == [child]
