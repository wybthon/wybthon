"""Unit tests for ErrorBoundary component logic (no browser stubs needed)."""

from wybthon.error_boundary import ErrorBoundary
from wybthon.vnode import VNode, to_text_vnode


def test_error_boundary_renders_children_when_no_error():
    eb = ErrorBoundary({"children": [to_text_vnode("child")]})
    result = eb.render()
    assert isinstance(result, VNode)


def test_error_boundary_renders_fallback_string_on_error():
    eb = ErrorBoundary({"fallback": "oops", "children": []})
    eb._error.set(RuntimeError("boom"))
    result = eb.render()
    assert isinstance(result, VNode)
    assert result.tag == "_text"
    assert result.props["nodeValue"] == "oops"


def test_error_boundary_renders_fallback_vnode_on_error():
    fallback_node = to_text_vnode("fallback content")
    eb = ErrorBoundary({"fallback": fallback_node, "children": []})
    eb._error.set(RuntimeError("boom"))
    result = eb.render()
    assert isinstance(result, VNode)
    assert result.tag == "_text"
    assert result.props["nodeValue"] == "fallback content"


def test_error_boundary_renders_callable_fallback():
    captured = {}

    def fallback_fn(error, reset):
        captured["error"] = error
        captured["reset"] = reset
        return to_text_vnode(f"Error: {error}")

    eb = ErrorBoundary({"fallback": fallback_fn, "children": []})
    eb._error.set(ValueError("bad"))
    result = eb.render()
    assert isinstance(result, VNode)
    assert result.tag == "_text"
    assert "bad" in result.props["nodeValue"]
    assert "error" in captured


def test_error_boundary_callable_fallback_without_reset():
    def fallback_fn(error):
        return to_text_vnode(f"Error: {error}")

    eb = ErrorBoundary({"fallback": fallback_fn, "children": []})
    eb._error.set(ValueError("bad"))
    result = eb.render()
    assert isinstance(result, VNode)
    assert result.tag == "_text"
    assert "bad" in result.props["nodeValue"]


def test_error_boundary_reset_clears_error():
    eb = ErrorBoundary({"fallback": "oops", "children": [to_text_vnode("child")]})
    eb._error.set(RuntimeError("boom"))

    assert eb._error.get() is not None
    eb.reset()
    assert eb._error.get() is None


def test_error_boundary_reset_key_auto_clears():
    eb = ErrorBoundary({"fallback": "oops", "children": [], "reset_key": "v1"})
    eb._error.set(RuntimeError("boom"))
    eb._last_reset_token = repr("v1")

    eb.props["reset_key"] = "v2"
    eb.render()
    assert eb._error.get() is None


def test_error_boundary_reset_keys_list():
    eb = ErrorBoundary({"fallback": "oops", "children": [], "reset_keys": [1, 2]})
    eb._error.set(RuntimeError("boom"))
    eb._last_reset_token = repr((1, 2))

    eb.props["reset_keys"] = [1, 3]
    eb.render()
    assert eb._error.get() is None


def test_error_boundary_default_fallback_message():
    eb = ErrorBoundary({"children": []})
    eb._error.set(RuntimeError("boom"))
    result = eb.render()
    assert isinstance(result, VNode)
    assert result.tag == "_text"
    assert result.props["nodeValue"] == "Something went wrong."


def test_error_boundary_fallback_fn_that_raises():
    def bad_fallback(error, reset):
        raise TypeError("fallback broken")

    eb = ErrorBoundary({"fallback": bad_fallback, "children": []})
    eb._error.set(RuntimeError("boom"))
    result = eb.render()
    assert isinstance(result, VNode)
    assert result.tag == "_text"
    assert result.props["nodeValue"] == "Error rendering fallback"
