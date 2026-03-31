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
