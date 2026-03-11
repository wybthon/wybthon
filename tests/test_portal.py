"""Tests for create_portal – rendering children into a different container."""

from conftest import StubNode, collect_texts

import wybthon as _wybthon_pkg  # noqa: F401


def test_portal_renders_into_target_container(wyb, root_element):
    portal_target = wyb["dom"].Element(node=StubNode(tag="div"))

    def App(props):
        return wyb["vdom"].h(
            "div",
            {},
            wyb["vdom"].h("p", {}, "In parent"),
            wyb["vdom"].create_portal(wyb["vdom"].h("p", {}, "In portal"), portal_target),
        )

    wyb["vdom"].render(wyb["vdom"].h(App, {}), root_element)

    parent_texts = collect_texts(root_element.element)
    portal_texts = collect_texts(portal_target.element)

    assert "In parent" in parent_texts
    assert "In portal" not in parent_texts
    assert "In portal" in portal_texts


def test_portal_renders_list_of_children(wyb, root_element):
    portal_target = wyb["dom"].Element(node=StubNode(tag="div"))

    children = [
        wyb["vdom"].h("p", {}, "Child A"),
        wyb["vdom"].h("p", {}, "Child B"),
    ]

    def App(props):
        return wyb["vdom"].h(
            "div",
            {},
            wyb["vdom"].create_portal(children, portal_target),
        )

    wyb["vdom"].render(wyb["vdom"].h(App, {}), root_element)

    portal_texts = collect_texts(portal_target.element)
    assert "Child A" in portal_texts
    assert "Child B" in portal_texts


def test_portal_unmount_cleans_up(wyb, root_element):
    portal_target = wyb["dom"].Element(node=StubNode(tag="div"))

    def App(props):
        return wyb["vdom"].h(
            "div",
            {},
            wyb["vdom"].create_portal(wyb["vdom"].h("span", {}, "Portal content"), portal_target),
        )

    tree = wyb["vdom"].h(App, {})
    wyb["vdom"].render(tree, root_element)

    assert "Portal content" in collect_texts(portal_target.element)

    wyb["vdom"]._unmount(tree)
    assert "Portal content" not in collect_texts(portal_target.element)


def test_portal_placeholder_in_parent(wyb, root_element):
    """Portal should leave an empty text placeholder in the parent container."""
    portal_target = wyb["dom"].Element(node=StubNode(tag="div"))

    def App(props):
        return wyb["vdom"].h(
            "div",
            {},
            wyb["vdom"].h("p", {}, "Before"),
            wyb["vdom"].create_portal(wyb["vdom"].h("p", {}, "Modal"), portal_target),
            wyb["vdom"].h("p", {}, "After"),
        )

    wyb["vdom"].render(wyb["vdom"].h(App, {}), root_element)

    parent_texts = collect_texts(root_element.element)
    assert "Before" in parent_texts
    assert "After" in parent_texts
    assert "Modal" not in parent_texts
    assert "Modal" in collect_texts(portal_target.element)
