import importlib

from conftest import StubNode

# Import wybthon BEFORE stubs so __init__.py runs with _IN_BROWSER=False
import wybthon  # noqa: F401


def _first_child(container):
    return container.element.childNodes[0]


def test_style_set_update_and_clear(browser_stubs):
    dom_mod = importlib.import_module("wybthon.dom")
    importlib.reload(dom_mod)
    vdom_mod = importlib.import_module("wybthon.vdom")
    importlib.reload(vdom_mod)

    root = dom_mod.Element(node=StubNode(tag="div"))

    # Initial styles
    view1 = vdom_mod.h("div", {"style": {"backgroundColor": "red", "fontSize": 14}})
    vdom_mod.render(view1, root)
    node = _first_child(root)
    assert node.style._props == {"background-color": "red", "font-size": "14"}

    # Update: remove backgroundColor, change fontSize, add marginTop
    view2 = vdom_mod.h("div", {"style": {"fontSize": 16, "marginTop": 2}})
    vdom_mod.render(view2, root)
    node = _first_child(root)
    assert node.style._props == {"font-size": "16", "margin-top": "2"}
    assert "background-color" not in node.style._props

    # Clear styles by setting style to None
    view3 = vdom_mod.h("div", {"style": None})
    vdom_mod.render(view3, root)
    node = _first_child(root)
    assert node.style._props == {}


def test_dataset_set_update_and_clear(browser_stubs):
    dom_mod = importlib.import_module("wybthon.dom")
    importlib.reload(dom_mod)
    vdom_mod = importlib.import_module("wybthon.vdom")
    importlib.reload(vdom_mod)

    root = dom_mod.Element(node=StubNode(tag="div"))

    # Initial dataset
    view1 = vdom_mod.h("div", {"dataset": {"id": "x", "role": "button"}})
    vdom_mod.render(view1, root)
    node = _first_child(root)
    assert node.getAttribute("data-id") == "x"
    assert node.getAttribute("data-role") == "button"

    # Update: change id, remove role
    view2 = vdom_mod.h("div", {"dataset": {"id": "y"}})
    vdom_mod.render(view2, root)
    node = _first_child(root)
    assert node.getAttribute("data-id") == "y"
    assert node.getAttribute("data-role") is None

    # Clear dataset with non-dict
    view3 = vdom_mod.h("div", {"dataset": "oops"})
    vdom_mod.render(view3, root)
    node = _first_child(root)
    assert node.getAttribute("data-id") is None


def test_value_property_update_and_removal(browser_stubs):
    dom_mod = importlib.import_module("wybthon.dom")
    importlib.reload(dom_mod)
    vdom_mod = importlib.import_module("wybthon.vdom")
    importlib.reload(vdom_mod)

    root = dom_mod.Element(node=StubNode(tag="div"))

    # Initial value
    view1 = vdom_mod.h("input", {"value": "abc"})
    vdom_mod.render(view1, root)
    node = _first_child(root)
    assert node.value == "abc"

    # Update value (number becomes string)
    view2 = vdom_mod.h("input", {"value": 42})
    vdom_mod.render(view2, root)
    node = _first_child(root)
    assert node.value == "42"

    # Remove value prop → should clear to empty string
    view3 = vdom_mod.h("input", {})
    vdom_mod.render(view3, root)
    node = _first_child(root)
    assert node.value == ""


def test_checked_property_toggle_and_removal(browser_stubs):
    dom_mod = importlib.import_module("wybthon.dom")
    importlib.reload(dom_mod)
    vdom_mod = importlib.import_module("wybthon.vdom")
    importlib.reload(vdom_mod)

    root = dom_mod.Element(node=StubNode(tag="div"))

    # Initially checked
    view1 = vdom_mod.h("input", {"checked": True})
    vdom_mod.render(view1, root)
    node = _first_child(root)
    assert node.checked is True

    # Toggle to False
    view2 = vdom_mod.h("input", {"checked": False})
    vdom_mod.render(view2, root)
    node = _first_child(root)
    assert node.checked is False

    # Remove checked prop → should clear to False
    view3 = vdom_mod.h("input", {})
    vdom_mod.render(view3, root)
    node = _first_child(root)
    assert node.checked is False
