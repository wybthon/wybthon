"""Unit tests for ErrorBoundary component logic."""

from wybthon.error_boundary import _compute_reset_token, _render_fallback
from wybthon.vnode import VNode, to_text_vnode


def test_compute_reset_token_none():
    assert _compute_reset_token({}) == ""


def test_compute_reset_token_single():
    assert _compute_reset_token({"reset_key": "v1"}) == repr("v1")


def test_compute_reset_token_list():
    assert _compute_reset_token({"reset_keys": [1, 2]}) == repr((1, 2))


def test_compute_reset_token_callable():
    assert _compute_reset_token({"reset_key": lambda: 42}) == repr(42)


def test_render_fallback_string():
    result = _render_fallback(RuntimeError("boom"), {"fallback": "oops"}, lambda: None)
    assert isinstance(result, VNode)
    assert result.tag == "_text"
    assert result.props["nodeValue"] == "oops"


def test_render_fallback_vnode():
    fb = to_text_vnode("fallback content")
    result = _render_fallback(RuntimeError("boom"), {"fallback": fb}, lambda: None)
    assert result.tag == "_text"
    assert result.props["nodeValue"] == "fallback content"


def test_render_fallback_callable():
    captured = {}

    def fallback_fn(error, reset):
        captured["error"] = error
        captured["reset"] = reset
        return to_text_vnode(f"Error: {error}")

    result = _render_fallback(ValueError("bad"), {"fallback": fallback_fn}, lambda: None)
    assert result.tag == "_text"
    assert "bad" in result.props["nodeValue"]
    assert "error" in captured


def test_render_fallback_callable_without_reset():
    def fallback_fn(error):
        return to_text_vnode(f"Error: {error}")

    result = _render_fallback(ValueError("bad"), {"fallback": fallback_fn}, lambda: None)
    assert result.tag == "_text"
    assert "bad" in result.props["nodeValue"]


def test_render_fallback_default():
    result = _render_fallback(RuntimeError("boom"), {}, lambda: None)
    assert result.tag == "_text"
    assert result.props["nodeValue"] == "Something went wrong."


def test_render_fallback_callable_that_raises():
    def bad_fallback(error, reset):
        raise TypeError("fallback broken")

    result = _render_fallback(RuntimeError("boom"), {"fallback": bad_fallback}, lambda: None)
    assert result.tag == "_text"
    assert result.props["nodeValue"] == "Error rendering fallback"
