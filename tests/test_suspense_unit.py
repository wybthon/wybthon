"""Unit tests for Suspense component logic.

These tests exercise the Suspense function component through the reconciler
using browser stubs, since Suspense uses get_props() and create_signal()
which require a component context.
"""

from conftest import collect_texts

import wybthon as _wybthon_pkg  # noqa: F401
from wybthon.reactivity import Signal as signal


class FakeResource:
    """Minimal resource stub with a loading signal."""

    def __init__(self, is_loading: bool = False):
        self.loading = signal(is_loading)


def test_suspense_renders_children_when_no_resources(wyb, root_element):
    vdom = wyb["vdom"]
    vdom.render(
        vdom.h(vdom.Suspense, {"children": [vdom.h("p", {}, "content")]}),
        root_element,
    )
    assert "content" in collect_texts(root_element.element)


def test_suspense_renders_fallback_when_loading(wyb, root_element):
    vdom = wyb["vdom"]
    res = FakeResource(is_loading=True)
    vdom.render(
        vdom.h(vdom.Suspense, {"resource": res, "fallback": "Loading...", "children": [vdom.h("p", {}, "data")]}),
        root_element,
    )
    assert "Loading..." in collect_texts(root_element.element)


def test_suspense_renders_children_when_loaded(wyb, root_element):
    vdom = wyb["vdom"]
    res = FakeResource(is_loading=False)
    vdom.render(
        vdom.h(vdom.Suspense, {"resource": res, "children": [vdom.h("p", {}, "data")]}),
        root_element,
    )
    assert "data" in collect_texts(root_element.element)


def test_suspense_multiple_resources_any_loading(wyb, root_element):
    vdom = wyb["vdom"]
    res1 = FakeResource(is_loading=False)
    res2 = FakeResource(is_loading=True)
    vdom.render(
        vdom.h(vdom.Suspense, {"resources": [res1, res2], "fallback": "Wait...", "children": []}),
        root_element,
    )
    assert "Wait..." in collect_texts(root_element.element)


def test_suspense_all_loaded(wyb, root_element):
    vdom = wyb["vdom"]
    res1 = FakeResource(is_loading=False)
    res2 = FakeResource(is_loading=False)
    vdom.render(
        vdom.h(vdom.Suspense, {"resources": [res1, res2], "children": [vdom.h("p", {}, "done")]}),
        root_element,
    )
    assert "done" in collect_texts(root_element.element)


def test_suspense_callable_fallback(wyb, root_element):
    vdom = wyb["vdom"]
    from wybthon.vnode import to_text_vnode

    res = FakeResource(is_loading=True)
    fb = lambda: to_text_vnode("custom loading")  # noqa: E731
    vdom.render(
        vdom.h(vdom.Suspense, {"resource": res, "fallback": fb, "children": []}),
        root_element,
    )
    assert "custom loading" in collect_texts(root_element.element)


def test_suspense_none_resources_filtered(wyb, root_element):
    vdom = wyb["vdom"]
    vdom.render(
        vdom.h(vdom.Suspense, {"resources": [None, None], "children": [vdom.h("p", {}, "ok")]}),
        root_element,
    )
    assert "ok" in collect_texts(root_element.element)


def test_suspense_normalize_single_child(wyb, root_element):
    vdom = wyb["vdom"]
    from wybthon.vnode import to_text_vnode

    vdom.render(
        vdom.h(vdom.Suspense, {"children": to_text_vnode("single")}),
        root_element,
    )
    assert "single" in collect_texts(root_element.element)
