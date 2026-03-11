import importlib

from conftest import StubNode, texts_of_children

# Import wybthon BEFORE stubs so __init__.py runs with _IN_BROWSER=False
import wybthon  # noqa: F401


def test_text_node_fast_path_identity_and_update(browser_stubs):
    dom_mod = importlib.import_module("wybthon.dom")
    importlib.reload(dom_mod)
    vdom_mod = importlib.import_module("wybthon.vdom")
    importlib.reload(vdom_mod)

    root = dom_mod.Element(node=StubNode(tag="div"))

    view1 = vdom_mod.h("div", {}, "hello")
    vdom_mod.render(view1, root)
    div1 = root.element.childNodes[0]
    assert len(div1.childNodes) == 1
    t1 = div1.childNodes[0]
    assert t1.nodeValue == "hello"

    view2 = vdom_mod.h("div", {}, "world")
    vdom_mod.render(view2, root)
    div2 = root.element.childNodes[0]
    t2 = div2.childNodes[0]
    assert t2 is t1
    assert t2.nodeValue == "world"


def test_unkeyed_text_children_reorder_content_and_identity_reuse(browser_stubs):
    dom_mod = importlib.import_module("wybthon.dom")
    importlib.reload(dom_mod)
    vdom_mod = importlib.import_module("wybthon.vdom")
    importlib.reload(vdom_mod)

    root = dom_mod.Element(node=StubNode(tag="div"))

    initial = ["A", "B", "C", "D"]
    view1 = vdom_mod.h("div", {}, *initial)
    vdom_mod.render(view1, root)
    div1 = root.element.childNodes[0]
    before_nodes = list(div1.childNodes)
    assert texts_of_children(div1) == initial

    target = ["C", "A", "D", "B"]
    view2 = vdom_mod.h("div", {}, *target)
    vdom_mod.render(view2, root)
    div2 = root.element.childNodes[0]
    after_nodes = list(div2.childNodes)
    assert texts_of_children(div2) == target

    # Ensure nodes were reused (no replacements), even if positions/content changed
    assert set(before_nodes) == set(after_nodes)
