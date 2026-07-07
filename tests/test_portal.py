"""Tests for create_portal – rendering children into a different container."""

from conftest import StubNode, collect_texts

import wybthon as _wybthon_pkg  # noqa: F401
from wybthon.portal import create_portal
from wybthon.vnode import h


def test_portal_renders_into_target_container(wyb, root_element):
    portal_target = wyb["dom"].Element(node=StubNode(tag="div"))

    def App(props):
        return h(
            "div",
            {},
            h("p", {}, "In parent"),
            create_portal(h("p", {}, "In portal"), portal_target),
        )

    wyb["reconciler"].render(h(App, {}), root_element)

    parent_texts = collect_texts(root_element.element)
    portal_texts = collect_texts(portal_target.element)

    assert "In parent" in parent_texts
    assert "In portal" not in parent_texts
    assert "In portal" in portal_texts


def test_portal_renders_list_of_children(wyb, root_element):
    portal_target = wyb["dom"].Element(node=StubNode(tag="div"))

    children = [
        h("p", {}, "Child A"),
        h("p", {}, "Child B"),
    ]

    def App(props):
        return h(
            "div",
            {},
            create_portal(children, portal_target),
        )

    wyb["reconciler"].render(h(App, {}), root_element)

    portal_texts = collect_texts(portal_target.element)
    assert "Child A" in portal_texts
    assert "Child B" in portal_texts


def test_portal_unmount_cleans_up(wyb, root_element):
    portal_target = wyb["dom"].Element(node=StubNode(tag="div"))

    def App(props):
        return h(
            "div",
            {},
            create_portal(h("span", {}, "Portal content"), portal_target),
        )

    tree = h(App, {})
    wyb["reconciler"].render(tree, root_element)

    assert "Portal content" in collect_texts(portal_target.element)

    wyb["reconciler"].unmount(tree)
    assert "Portal content" not in collect_texts(portal_target.element)


def test_portal_placeholder_in_parent(wyb, root_element):
    """Portal should leave an empty text placeholder in the parent container."""
    portal_target = wyb["dom"].Element(node=StubNode(tag="div"))

    def App(props):
        return h(
            "div",
            {},
            h("p", {}, "Before"),
            create_portal(h("p", {}, "Modal"), portal_target),
            h("p", {}, "After"),
        )

    wyb["reconciler"].render(h(App, {}), root_element)

    parent_texts = collect_texts(root_element.element)
    assert "Before" in parent_texts
    assert "After" in parent_texts
    assert "Modal" not in parent_texts
    assert "Modal" in collect_texts(portal_target.element)
