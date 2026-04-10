"""Tests for the HTML element helpers and Fragment."""

import importlib

from conftest import StubNode

# Import wybthon BEFORE stubs so __init__.py runs with _IN_BROWSER=False
import wybthon  # noqa: F401


def _load_modules():
    """Reload dom, vdom, html modules against current stubs. Returns (dom_mod, vdom_mod, html_mod)."""
    dom_mod = importlib.import_module("wybthon.dom")
    importlib.reload(dom_mod)
    vdom_mod = importlib.import_module("wybthon.vdom")
    importlib.reload(vdom_mod)
    html_mod = importlib.import_module("wybthon.html")
    importlib.reload(html_mod)
    return dom_mod, vdom_mod, html_mod


# ── VNode creation tests ──


def test_div_creates_correct_vnode(browser_stubs):
    _, vdom_mod, html_mod = _load_modules()
    node = html_mod.div("Hello", class_name="box")
    assert node.tag == "div"
    assert node.props.get("class") == "box"
    assert len(node.children) == 1


def test_class_name_maps_to_class(browser_stubs):
    _, _, html_mod = _load_modules()
    node = html_mod.span(class_name="highlight")
    assert node.props.get("class") == "highlight"
    assert "class_name" not in node.props


def test_html_for_maps_to_for(browser_stubs):
    _, _, html_mod = _load_modules()
    node = html_mod.label("Name", html_for="name-input")
    assert node.props.get("for") == "name-input"
    assert "html_for" not in node.props


def test_children_as_positional_args(browser_stubs):
    _, _, html_mod = _load_modules()
    node = html_mod.ul(
        html_mod.li("Item 1"),
        html_mod.li("Item 2"),
        html_mod.li("Item 3"),
    )
    assert node.tag == "ul"
    assert len(node.children) == 3
    assert all(c.tag == "li" for c in node.children)


def test_no_children_no_props(browser_stubs):
    _, _, html_mod = _load_modules()
    node = html_mod.br()
    assert node.tag == "br"
    assert len(node.children) == 0
    assert node.props == {}


def test_event_handlers_pass_through(browser_stubs):
    _, _, html_mod = _load_modules()
    handler = lambda e: None  # noqa: E731
    node = html_mod.button("Click", on_click=handler)
    assert node.tag == "button"
    assert node.props.get("on_click") is handler


def test_style_dict_passes_through(browser_stubs):
    _, _, html_mod = _load_modules()
    node = html_mod.div(style={"color": "red", "fontSize": 14})
    assert node.props["style"] == {"color": "red", "fontSize": 14}


def test_input_helper_name(browser_stubs):
    _, _, html_mod = _load_modules()
    node = html_mod.input_(type="text", value="hello")
    assert node.tag == "input"
    assert node.props.get("type") == "text"
    assert node.props.get("value") == "hello"


def test_main_helper_name(browser_stubs):
    _, _, html_mod = _load_modules()
    node = html_mod.main_("Content")
    assert node.tag == "main"


def test_mixed_children_and_props(browser_stubs):
    _, _, html_mod = _load_modules()
    node = html_mod.a("Click here", href="/about", class_name="link")
    assert node.tag == "a"
    assert node.props.get("href") == "/about"
    assert node.props.get("class") == "link"
    assert len(node.children) == 1


def test_select_with_options(browser_stubs):
    _, _, html_mod = _load_modules()
    node = html_mod.select(
        html_mod.option("One", value="1"),
        html_mod.option("Two", value="2"),
        id="my-select",
    )
    assert node.tag == "select"
    assert node.props.get("id") == "my-select"
    assert len(node.children) == 2
    assert node.children[0].tag == "option"
    assert node.children[0].props.get("value") == "1"


# ── Fragment tests ──


def test_fragment_creates_fragment_vnode(browser_stubs):
    _, vdom_mod, _ = _load_modules()
    frag = vdom_mod.Fragment(
        vdom_mod.h("p", {}, "A"),
        vdom_mod.h("p", {}, "B"),
    )
    assert frag.tag == "_fragment"
    assert frag.props == {}
    assert len(frag.children) == 2


def test_fragment_with_no_children(browser_stubs):
    _, vdom_mod, _ = _load_modules()
    frag = vdom_mod.Fragment()
    assert frag.tag == "_fragment"
    assert frag.props == {}
    assert len(frag.children) == 0


def test_fragment_called_as_component(browser_stubs):
    """When Fragment is used via h(Fragment, {}, ...) it receives a props dict."""
    _, vdom_mod, _ = _load_modules()
    child_a = vdom_mod.h("p", {}, "A")
    child_b = vdom_mod.h("p", {}, "B")
    frag = vdom_mod.Fragment({"children": [child_a, child_b]})
    assert frag.tag == "_fragment"
    assert frag.props == {}
    assert len(frag.children) == 2


def test_fragment_renders_to_dom(browser_stubs):
    dom_mod, vdom_mod, _ = _load_modules()
    root = dom_mod.Element(node=StubNode(tag="div"))
    tree = vdom_mod.Fragment(
        vdom_mod.h("p", {}, "First"),
        vdom_mod.h("p", {}, "Second"),
    )
    vdom_mod.render(tree, root)
    children = root.element.childNodes
    assert len(children) == 4  # comment_start, p, p, comment_end
    assert getattr(children[0], "_is_comment", False) is True
    assert children[1].tag == "p"
    assert children[1].childNodes[0].nodeValue == "First"
    assert children[2].tag == "p"
    assert children[2].childNodes[0].nodeValue == "Second"
    assert getattr(children[3], "_is_comment", False) is True


def test_fragment_in_function_component(browser_stubs):
    dom_mod, vdom_mod, html_mod = _load_modules()
    root = dom_mod.Element(node=StubNode(tag="div"))

    def MyComp(_props):
        return vdom_mod.Fragment(
            vdom_mod.h("h1", {}, "Title"),
            vdom_mod.h("p", {}, "Body"),
        )

    tree = vdom_mod.h(MyComp, {})
    vdom_mod.render(tree, root)
    children = root.element.childNodes
    assert len(children) == 4  # comment_start, h1, p, comment_end
    assert getattr(children[0], "_is_comment", False) is True
    assert children[1].tag == "h1"
    assert children[2].tag == "p"
    assert getattr(children[3], "_is_comment", False) is True


# ── _is_event_prop fix tests ──


def test_is_event_prop_snake_case(browser_stubs):
    _, vdom_mod, _ = _load_modules()
    assert vdom_mod._is_event_prop("on_click") is True
    assert vdom_mod._is_event_prop("on_submit") is True
    assert vdom_mod._is_event_prop("on_mouseover") is True


def test_is_event_prop_camel_case(browser_stubs):
    _, vdom_mod, _ = _load_modules()
    assert vdom_mod._is_event_prop("onClick") is True
    assert vdom_mod._is_event_prop("onSubmit") is True
    assert vdom_mod._is_event_prop("onChange") is True


def test_is_event_prop_rejects_non_events(browser_stubs):
    _, vdom_mod, _ = _load_modules()
    assert vdom_mod._is_event_prop("one") is False
    assert vdom_mod._is_event_prop("only") is False
    assert vdom_mod._is_event_prop("onset") is False
    assert vdom_mod._is_event_prop("on") is False
    assert vdom_mod._is_event_prop("online") is False


# ── HTML helpers render to DOM ──


def test_html_helpers_render_to_dom(browser_stubs):
    dom_mod, vdom_mod, html_mod = _load_modules()
    root = dom_mod.Element(node=StubNode(tag="div"))
    tree = html_mod.div(
        html_mod.h1("Hello"),
        html_mod.p("World"),
        class_name="container",
    )
    vdom_mod.render(tree, root)
    container = root.element.childNodes[0]
    assert container.tag == "div"
    assert container.getAttribute("class") == "container"
    assert len(container.childNodes) == 2
    assert container.childNodes[0].tag == "h1"
    assert container.childNodes[1].tag == "p"


def test_html_helpers_patch_correctly(browser_stubs):
    dom_mod, vdom_mod, html_mod = _load_modules()
    root = dom_mod.Element(node=StubNode(tag="div"))

    tree1 = html_mod.div(html_mod.p("Before"), class_name="v1")
    vdom_mod.render(tree1, root)
    node = root.element.childNodes[0]
    assert node.getAttribute("class") == "v1"
    assert node.childNodes[0].childNodes[0].nodeValue == "Before"

    tree2 = html_mod.div(html_mod.p("After"), class_name="v2")
    vdom_mod.render(tree2, root)
    node = root.element.childNodes[0]
    assert node.getAttribute("class") == "v2"
    assert node.childNodes[0].childNodes[0].nodeValue == "After"


def test_spread_props_with_html_helpers(browser_stubs):
    """Spreading dicts via ** should work with keyword args."""
    _, _, html_mod = _load_modules()
    bindings = {"value": "test", "on_input": lambda e: None}
    node = html_mod.input_(type="text", **bindings, class_name="field")
    assert node.props.get("type") == "text"
    assert node.props.get("value") == "test"
    assert node.props.get("class") == "field"
    assert callable(node.props.get("on_input"))
