"""Unit tests for Suspense component logic (no browser stubs needed)."""

from wybthon.reactivity import signal
from wybthon.suspense import Suspense
from wybthon.vnode import VNode, to_text_vnode


class FakeResource:
    """Minimal resource stub with a loading signal."""

    def __init__(self, is_loading: bool = False):
        self.loading = signal(is_loading)


def test_suspense_renders_children_when_no_resources():
    s = Suspense({"children": [to_text_vnode("content")]})
    result = s.render()
    assert isinstance(result, VNode)


def test_suspense_renders_fallback_when_loading():
    res = FakeResource(is_loading=True)
    s = Suspense({"resource": res, "fallback": "Loading...", "children": [to_text_vnode("content")]})
    result = s.render()
    assert result.tag == "_text"
    assert result.props["nodeValue"] == "Loading..."


def test_suspense_renders_children_when_loaded():
    res = FakeResource(is_loading=False)
    s = Suspense({"resource": res, "children": [to_text_vnode("data")]})
    result = s.render()
    assert isinstance(result, VNode)


def test_suspense_multiple_resources():
    res1 = FakeResource(is_loading=False)
    res2 = FakeResource(is_loading=True)
    s = Suspense({"resources": [res1, res2], "fallback": "Wait...", "children": []})
    result = s.render()
    assert result.props["nodeValue"] == "Wait..."


def test_suspense_all_loaded():
    res1 = FakeResource(is_loading=False)
    res2 = FakeResource(is_loading=False)
    s = Suspense({"resources": [res1, res2], "children": [to_text_vnode("done")]})
    result = s.render()
    assert isinstance(result, VNode)


def test_suspense_callable_fallback():
    res = FakeResource(is_loading=True)

    def fb():
        return to_text_vnode("custom loading")

    s = Suspense({"resource": res, "fallback": fb, "children": []})
    result = s.render()
    assert result.props["nodeValue"] == "custom loading"


def test_suspense_keep_previous():
    res = FakeResource(is_loading=False)
    s = Suspense({"resource": res, "fallback": "Wait...", "keep_previous": True, "children": [to_text_vnode("data")]})

    result = s.render()
    assert s._has_completed_once is True

    res.loading.set(True)
    result = s.render()
    assert isinstance(result, VNode)


def test_suspense_default_fallback():
    res = FakeResource(is_loading=True)
    s = Suspense({"resource": res, "children": []})
    result = s.render()
    assert result.tag == "_text"


def test_suspense_none_resources_filtered():
    s = Suspense({"resources": [None, None], "children": [to_text_vnode("ok")]})
    result = s.render()
    assert isinstance(result, VNode)


def test_suspense_normalize_single_child():
    s = Suspense({"children": to_text_vnode("single")})
    result = s.render()
    assert isinstance(result, VNode)
