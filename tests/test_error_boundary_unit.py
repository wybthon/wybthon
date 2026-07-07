"""Unit tests for ErrorBoundary component logic."""

from conftest import collect_texts

from wybthon.error_boundary import ErrorBoundary, _compute_reset_token, _render_fallback
from wybthon.reactivity import ReactiveProps
from wybthon.vnode import VNode, h, to_text_vnode


def _props(d):
    return ReactiveProps(d)


def test_compute_reset_token_none():
    assert _compute_reset_token(_props({})) == ""


def test_compute_reset_token_single():
    assert _compute_reset_token(_props({"reset_key": "v1"})) == repr("v1")


def test_compute_reset_token_list():
    assert _compute_reset_token(_props({"reset_keys": [1, 2]})) == repr((1, 2))


def test_compute_reset_token_callable():
    assert _compute_reset_token(_props({"reset_key": lambda: 42})) == repr(42)


def test_render_fallback_string():
    result = _render_fallback(RuntimeError("boom"), _props({"fallback": "oops"}), lambda: None)
    assert isinstance(result, VNode)
    assert result.tag == "_text"
    assert result.props["nodeValue"] == "oops"


def test_render_fallback_vnode():
    fb = to_text_vnode("fallback content")
    result = _render_fallback(RuntimeError("boom"), _props({"fallback": fb}), lambda: None)
    assert result.tag == "_text"
    assert result.props["nodeValue"] == "fallback content"


def test_render_fallback_callable():
    captured = {}

    def fallback_fn(error, reset):
        captured["error"] = error
        captured["reset"] = reset
        return to_text_vnode(f"Error: {error}")

    result = _render_fallback(ValueError("bad"), _props({"fallback": fallback_fn}), lambda: None)
    assert result.tag == "_text"
    assert "bad" in result.props["nodeValue"]
    assert "error" in captured


def test_render_fallback_callable_without_reset():
    def fallback_fn(error):
        return to_text_vnode(f"Error: {error}")

    result = _render_fallback(ValueError("bad"), _props({"fallback": fallback_fn}), lambda: None)
    assert result.tag == "_text"
    assert "bad" in result.props["nodeValue"]


def test_render_fallback_default():
    result = _render_fallback(RuntimeError("boom"), _props({}), lambda: None)
    assert result.tag == "_text"
    assert result.props["nodeValue"] == "Something went wrong."


def test_render_fallback_callable_that_raises():
    def bad_fallback(error, reset):
        raise TypeError("fallback broken")

    result = _render_fallback(RuntimeError("boom"), _props({"fallback": bad_fallback}), lambda: None)
    assert result.tag == "_text"
    assert result.props["nodeValue"] == "Error rendering fallback"


# --------------------------------------------------------------------------- #
# Mount-time behaviour: catching errors thrown while mounting children.
#
# Regression coverage for the reconciler routing synchronous child mount/render
# errors to the nearest ErrorBoundary instead of swallowing them at its
# defensive try/except sites. Without that routing the fallback never renders.
# --------------------------------------------------------------------------- #


def test_error_boundary_catches_child_mount_error(wyb, root_element):
    """A child that raises during mount triggers the boundary's fallback."""
    vdom = wyb["reconciler"]
    reactivity = wyb["reactivity"]

    should_throw = reactivity.signal(True)

    def Bug(props):
        if should_throw.get():
            raise RuntimeError("boom")
        return h("span", {}, "ok")

    def fallback(err, reset):
        return h("span", {}, f"caught: {err}")

    def App(props):
        return h(
            ErrorBoundary,
            {"fallback": fallback},
            h("div", {}, h(Bug, {})),
        )

    vdom.render(h(App, {}), root_element)

    texts = collect_texts(root_element.element)
    assert any("caught: boom" in t for t in texts), texts
    assert not any(t == "ok" for t in texts), texts


def test_error_boundary_recovers_after_reset(wyb, root_element):
    """Fixing the child and bumping ``reset_key`` clears the boundary."""
    vdom = wyb["reconciler"]
    reactivity = wyb["reactivity"]

    should_throw = reactivity.signal(True)
    reset_key = reactivity.signal(0)

    def Bug(props):
        if should_throw.get():
            raise RuntimeError("boom")
        return h("span", {}, "recovered")

    def fallback(err, reset):
        return h("span", {}, f"caught: {err}")

    def App(props):
        return h(
            ErrorBoundary,
            {"fallback": fallback, "reset_key": reset_key.get},
            h("div", {}, h(Bug, {})),
        )

    vdom.render(h(App, {}), root_element)
    assert any("caught: boom" in t for t in collect_texts(root_element.element))

    should_throw.set(False)
    reset_key.set(1)

    texts = collect_texts(root_element.element)
    assert any("recovered" in t for t in texts), texts
    assert not any("caught: boom" in t for t in texts), texts
