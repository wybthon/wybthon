"""Tests for the HTML element helpers and Fragment."""

import importlib
import sys
from types import ModuleType


class _ClassList:
    def __init__(self):
        self._set = set()

    def add(self, name):
        self._set.add(name)

    def remove(self, name):
        self._set.discard(name)

    def contains(self, name):
        return name in self._set


class _Style:
    def __init__(self):
        self._props = {}

    def setProperty(self, name, value):
        self._props[name] = str(value)

    def removeProperty(self, name):
        self._props.pop(name, None)


class _Node:
    def __init__(self, tag=None, text=None):
        self.tag = tag
        self.nodeValue = text
        self.parentNode = None
        self.childNodes = []
        self.attributes = {}
        self.classList = _ClassList()
        self.style = _Style()
        self.value = ""
        self.checked = False

    @property
    def nextSibling(self):
        if self.parentNode is None:
            return None
        try:
            idx = self.parentNode.childNodes.index(self)
        except ValueError:
            return None
        return self.parentNode.childNodes[idx + 1] if idx + 1 < len(self.parentNode.childNodes) else None

    def appendChild(self, node):
        if getattr(node, "parentNode", None) is not None:
            try:
                p = node.parentNode
                p.childNodes.remove(node)
            except Exception:
                pass
        node.parentNode = self
        self.childNodes.append(node)
        return node

    def insertBefore(self, node, anchor):
        if getattr(node, "parentNode", None) is not None:
            try:
                p = node.parentNode
                p.childNodes.remove(node)
            except Exception:
                pass
        node.parentNode = self
        if anchor is None:
            self.childNodes.append(node)
            return node
        try:
            idx = self.childNodes.index(anchor)
        except ValueError:
            self.childNodes.append(node)
            return node
        self.childNodes.insert(idx, node)
        return node

    def removeChild(self, node):
        try:
            self.childNodes.remove(node)
            node.parentNode = None
            return node
        except ValueError:
            return node

    def setAttribute(self, name, value):
        self.attributes[name] = str(value)

    def getAttribute(self, name):
        return self.attributes.get(name)

    def removeAttribute(self, name):
        self.attributes.pop(name, None)


class _Document:
    def __init__(self):
        self._listeners = {}

    def createElement(self, tag):
        return _Node(tag=tag)

    def createTextNode(self, text):
        return _Node(text=str(text))

    def addEventListener(self, event_type, proxy):
        self._listeners.setdefault(event_type, set()).add(proxy)

    def removeEventListener(self, event_type, proxy):
        s = self._listeners.get(event_type)
        if s is not None and proxy in s:
            s.remove(proxy)


def _install_stubs():
    saved = {name: sys.modules.get(name) for name in ("js", "pyodide", "pyodide.ffi")}
    js_mod = ModuleType("js")
    js_mod.document = _Document()
    js_mod.fetch = lambda url: None
    sys.modules["js"] = js_mod

    pyodide = ModuleType("pyodide")
    ffi = ModuleType("pyodide.ffi")
    ffi.create_proxy = lambda fn: fn
    sys.modules["pyodide"] = pyodide
    sys.modules["pyodide.ffi"] = ffi
    setattr(pyodide, "ffi", ffi)
    return saved


def _restore(saved):
    for name, mod in saved.items():
        if mod is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = mod


def _load_modules():
    dom_mod = importlib.import_module("wybthon.dom")
    importlib.reload(dom_mod)
    vdom_mod = importlib.import_module("wybthon.vdom")
    importlib.reload(vdom_mod)
    html_mod = importlib.import_module("wybthon.html")
    importlib.reload(html_mod)
    return dom_mod, vdom_mod, html_mod


# ── VNode creation tests ──


def test_div_creates_correct_vnode():
    saved = _install_stubs()
    try:
        _, vdom_mod, html_mod = _load_modules()
        node = html_mod.div("Hello", class_name="box")
        assert node.tag == "div"
        assert node.props.get("class") == "box"
        assert len(node.children) == 1
    finally:
        _restore(saved)


def test_class_name_maps_to_class():
    saved = _install_stubs()
    try:
        _, _, html_mod = _load_modules()
        node = html_mod.span(class_name="highlight")
        assert node.props.get("class") == "highlight"
        assert "class_name" not in node.props
    finally:
        _restore(saved)


def test_html_for_maps_to_for():
    saved = _install_stubs()
    try:
        _, _, html_mod = _load_modules()
        node = html_mod.label("Name", html_for="name-input")
        assert node.props.get("for") == "name-input"
        assert "html_for" not in node.props
    finally:
        _restore(saved)


def test_children_as_positional_args():
    saved = _install_stubs()
    try:
        _, _, html_mod = _load_modules()
        node = html_mod.ul(
            html_mod.li("Item 1"),
            html_mod.li("Item 2"),
            html_mod.li("Item 3"),
        )
        assert node.tag == "ul"
        assert len(node.children) == 3
        assert all(c.tag == "li" for c in node.children)
    finally:
        _restore(saved)


def test_no_children_no_props():
    saved = _install_stubs()
    try:
        _, _, html_mod = _load_modules()
        node = html_mod.br()
        assert node.tag == "br"
        assert len(node.children) == 0
        assert node.props == {}
    finally:
        _restore(saved)


def test_event_handlers_pass_through():
    saved = _install_stubs()
    try:
        _, _, html_mod = _load_modules()
        handler = lambda e: None  # noqa: E731
        node = html_mod.button("Click", on_click=handler)
        assert node.tag == "button"
        assert node.props.get("on_click") is handler
    finally:
        _restore(saved)


def test_style_dict_passes_through():
    saved = _install_stubs()
    try:
        _, _, html_mod = _load_modules()
        node = html_mod.div(style={"color": "red", "fontSize": 14})
        assert node.props["style"] == {"color": "red", "fontSize": 14}
    finally:
        _restore(saved)


def test_input_helper_name():
    saved = _install_stubs()
    try:
        _, _, html_mod = _load_modules()
        node = html_mod.input_(type="text", value="hello")
        assert node.tag == "input"
        assert node.props.get("type") == "text"
        assert node.props.get("value") == "hello"
    finally:
        _restore(saved)


def test_main_helper_name():
    saved = _install_stubs()
    try:
        _, _, html_mod = _load_modules()
        node = html_mod.main_("Content")
        assert node.tag == "main"
    finally:
        _restore(saved)


def test_mixed_children_and_props():
    saved = _install_stubs()
    try:
        _, _, html_mod = _load_modules()
        node = html_mod.a("Click here", href="/about", class_name="link")
        assert node.tag == "a"
        assert node.props.get("href") == "/about"
        assert node.props.get("class") == "link"
        assert len(node.children) == 1
    finally:
        _restore(saved)


def test_select_with_options():
    saved = _install_stubs()
    try:
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
    finally:
        _restore(saved)


# ── Fragment tests ──


def test_fragment_creates_span_with_display_contents():
    saved = _install_stubs()
    try:
        _, vdom_mod, _ = _load_modules()
        frag = vdom_mod.Fragment(
            vdom_mod.h("p", {}, "A"),
            vdom_mod.h("p", {}, "B"),
        )
        assert frag.tag == "span"
        assert frag.props.get("style") == {"display": "contents"}
        assert len(frag.children) == 2
    finally:
        _restore(saved)


def test_fragment_with_no_children():
    saved = _install_stubs()
    try:
        _, vdom_mod, _ = _load_modules()
        frag = vdom_mod.Fragment()
        assert frag.tag == "span"
        assert len(frag.children) == 0
    finally:
        _restore(saved)


def test_fragment_called_as_component():
    """When Fragment is used via h(Fragment, {}, ...) it receives a props dict."""
    saved = _install_stubs()
    try:
        _, vdom_mod, _ = _load_modules()
        child_a = vdom_mod.h("p", {}, "A")
        child_b = vdom_mod.h("p", {}, "B")
        frag = vdom_mod.Fragment({"children": [child_a, child_b]})
        assert frag.tag == "span"
        assert len(frag.children) == 2
    finally:
        _restore(saved)


def test_fragment_renders_to_dom():
    saved = _install_stubs()
    try:
        dom_mod, vdom_mod, _ = _load_modules()
        root = dom_mod.Element(node=_Node(tag="div"))
        tree = vdom_mod.Fragment(
            vdom_mod.h("p", {}, "First"),
            vdom_mod.h("p", {}, "Second"),
        )
        vdom_mod.render(tree, root)
        el = root.element.childNodes[0]
        assert el.tag == "span"
        assert el.style._props.get("display") == "contents"
        assert len(el.childNodes) == 2
        assert el.childNodes[0].childNodes[0].nodeValue == "First"
        assert el.childNodes[1].childNodes[0].nodeValue == "Second"
    finally:
        _restore(saved)


def test_fragment_in_function_component():
    saved = _install_stubs()
    try:
        dom_mod, vdom_mod, html_mod = _load_modules()
        root = dom_mod.Element(node=_Node(tag="div"))

        def MyComp(_props):
            return vdom_mod.Fragment(
                vdom_mod.h("h1", {}, "Title"),
                vdom_mod.h("p", {}, "Body"),
            )

        tree = vdom_mod.h(MyComp, {})
        vdom_mod.render(tree, root)
        span_el = root.element.childNodes[0]
        assert span_el.tag == "span"
        assert len(span_el.childNodes) == 2
    finally:
        _restore(saved)


# ── _is_event_prop fix tests ──


def test_is_event_prop_snake_case():
    saved = _install_stubs()
    try:
        _, vdom_mod, _ = _load_modules()
        assert vdom_mod._is_event_prop("on_click") is True
        assert vdom_mod._is_event_prop("on_submit") is True
        assert vdom_mod._is_event_prop("on_mouseover") is True
    finally:
        _restore(saved)


def test_is_event_prop_camel_case():
    saved = _install_stubs()
    try:
        _, vdom_mod, _ = _load_modules()
        assert vdom_mod._is_event_prop("onClick") is True
        assert vdom_mod._is_event_prop("onSubmit") is True
        assert vdom_mod._is_event_prop("onChange") is True
    finally:
        _restore(saved)


def test_is_event_prop_rejects_non_events():
    saved = _install_stubs()
    try:
        _, vdom_mod, _ = _load_modules()
        assert vdom_mod._is_event_prop("one") is False
        assert vdom_mod._is_event_prop("only") is False
        assert vdom_mod._is_event_prop("onset") is False
        assert vdom_mod._is_event_prop("on") is False
        assert vdom_mod._is_event_prop("online") is False
    finally:
        _restore(saved)


# ── HTML helpers render to DOM ──


def test_html_helpers_render_to_dom():
    saved = _install_stubs()
    try:
        dom_mod, vdom_mod, html_mod = _load_modules()
        root = dom_mod.Element(node=_Node(tag="div"))
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
    finally:
        _restore(saved)


def test_html_helpers_patch_correctly():
    saved = _install_stubs()
    try:
        dom_mod, vdom_mod, html_mod = _load_modules()
        root = dom_mod.Element(node=_Node(tag="div"))

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
    finally:
        _restore(saved)


def test_spread_props_with_html_helpers():
    """Spreading dicts via ** should work with keyword args."""
    saved = _install_stubs()
    try:
        _, _, html_mod = _load_modules()
        bindings = {"value": "test", "on_input": lambda e: None}
        node = html_mod.input_(type="text", **bindings, class_name="field")
        assert node.props.get("type") == "text"
        assert node.props.get("value") == "test"
        assert node.props.get("class") == "field"
        assert callable(node.props.get("on_input"))
    finally:
        _restore(saved)
