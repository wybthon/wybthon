"""A small in-memory DOM for server rendering, plus its HTML serializer.

The server renders through the ordinary reconciler and kernel wire
protocol, applied by [`PythonBackend`][wybthon.kernel.PythonBackend] to
this document. Reusing the real renderer means the server produces
exactly the node structure the browser's hydration pass expects.

Only the operations the kernel protocol needs are implemented. Nodes
are doubly linked so inserts, removals, and sibling walks are O(1).
"""

from __future__ import annotations

from html import escape
from typing import Any, Iterator

from .kernel import PythonBackend

__all__ = ["ServerDocument", "ServerBackend", "serialize_children", "serialize_node"]

VOID_ELEMENTS = frozenset(
    {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
)
_RAW_TEXT = frozenset({"script", "style", "xmp", "iframe", "noembed", "noframes", "noscript"})
# The HTML parser drops a newline that immediately follows these start tags.
_LEADING_NEWLINE = frozenset({"pre", "textarea", "listing"})


class _Style:
    """Ordered CSS declarations for one element."""

    __slots__ = ("decls",)

    def __init__(self) -> None:
        self.decls: dict[str, str] = {}

    def setProperty(self, name: str, value: Any) -> None:  # noqa: N802 - DOM API
        self.decls[name] = str(value)

    def removeProperty(self, name: str) -> None:  # noqa: N802 - DOM API
        self.decls.pop(name, None)

    def parse(self, text: str) -> None:
        self.decls.clear()
        for decl in text.split(";"):
            if ":" in decl:
                name, value = decl.split(":", 1)
                if name.strip():
                    self.decls[name.strip()] = value.strip()

    def text(self) -> str:
        return "; ".join(f"{k}: {v}" for k, v in self.decls.items())


class _Node:
    __slots__ = ("parentNode", "firstChild", "lastChild", "previousSibling", "nextSibling", "_wyb_id", "__dict__")

    tag: str | None = None
    _is_text = False
    _is_comment = False
    nodeValue: str | None = None

    def __init__(self) -> None:
        self.parentNode: _Node | None = None
        self.firstChild: _Node | None = None
        self.lastChild: _Node | None = None
        self.previousSibling: _Node | None = None
        self.nextSibling: _Node | None = None

    @property
    def childNodes(self) -> list[_Node]:  # noqa: N802 - DOM API
        return list(self._children())

    def _children(self) -> Iterator[_Node]:
        node = self.firstChild
        while node is not None:
            yield node
            node = node.nextSibling

    def _detach(self) -> None:
        parent = self.parentNode
        if parent is None:
            return
        prev, following = self.previousSibling, self.nextSibling
        if prev is None:
            parent.firstChild = following
        else:
            prev.nextSibling = following
        if following is None:
            parent.lastChild = prev
        else:
            following.previousSibling = prev
        self.parentNode = self.previousSibling = self.nextSibling = None

    def insertBefore(self, node: _Node, anchor: _Node | None) -> _Node:  # noqa: N802 - DOM API
        if anchor is not None and anchor.parentNode is not self:
            anchor = None
        if node is anchor:
            return node
        node._detach()
        node.parentNode = self
        if anchor is None:
            prev = self.lastChild
            node.previousSibling = prev
            if prev is None:
                self.firstChild = node
            else:
                prev.nextSibling = node
            self.lastChild = node
        else:
            prev = anchor.previousSibling
            node.previousSibling = prev
            node.nextSibling = anchor
            anchor.previousSibling = node
            if prev is None:
                self.firstChild = node
            else:
                prev.nextSibling = node
        return node

    def appendChild(self, node: _Node) -> _Node:  # noqa: N802 - DOM API
        return self.insertBefore(node, None)

    def removeChild(self, node: _Node) -> _Node:  # noqa: N802 - DOM API
        if node.parentNode is self:
            node._detach()
        return node

    def addEventListener(self, *_args: Any) -> None:  # noqa: N802 - DOM API
        """Server nodes never dispatch events."""

    def removeEventListener(self, *_args: Any) -> None:  # noqa: N802 - DOM API
        """Server nodes never dispatch events."""


class ServerElement(_Node):
    """An element node."""

    def __init__(self, tag: str, namespace: str | None = None) -> None:
        super().__init__()
        self.tag = tag
        self.namespaceURI = namespace
        self.attributes: dict[str, str] = {}
        self.style = _Style()
        self.value: Any = None
        self.checked: Any = None
        self.selected: Any = None
        self.selectedValues: Any = None
        self.innerHTML: str | None = None

    def setAttribute(self, name: str, value: Any) -> None:  # noqa: N802 - DOM API
        if name == "style":
            self.style.parse(str(value))
        self.attributes[name] = str(value)

    def getAttribute(self, name: str) -> str | None:  # noqa: N802 - DOM API
        if name == "style" and self.style.decls:
            return self.style.text()
        return self.attributes.get(name)

    def removeAttribute(self, name: str) -> None:  # noqa: N802 - DOM API
        if name == "style":
            self.style.decls.clear()
        self.attributes.pop(name, None)


class ServerText(_Node):
    """A text node."""

    _is_text = True

    def __init__(self, text: str) -> None:
        super().__init__()
        self.nodeValue = text


class ServerComment(_Node):
    """A comment node (hole anchors and fragment markers)."""

    _is_text = True
    _is_comment = True

    def __init__(self, text: str) -> None:
        super().__init__()
        self.nodeValue = text


class ServerDocument:
    """The factory side of the DOM API that `PythonBackend` calls."""

    def createElement(self, tag: str) -> ServerElement:  # noqa: N802 - DOM API
        return ServerElement(tag)

    def createElementNS(self, namespace: str, tag: str) -> ServerElement:  # noqa: N802 - DOM API
        return ServerElement(tag, namespace)

    def createTextNode(self, text: Any) -> ServerText:  # noqa: N802 - DOM API
        return ServerText(str(text))

    def createComment(self, text: Any = "") -> ServerComment:  # noqa: N802 - DOM API
        return ServerComment(str(text))

    def addEventListener(self, *_args: Any) -> None:  # noqa: N802 - DOM API
        """The server document never dispatches events."""

    def removeEventListener(self, *_args: Any) -> None:  # noqa: N802 - DOM API
        """The server document never dispatches events."""

    def querySelector(self, _selector: str) -> None:  # noqa: N802 - DOM API
        """Selectors don't resolve on the server; render into a created container."""
        return None


class ServerBackend(PythonBackend):
    """The kernel backend used for server rendering.

    It never parses templates, so every element mounts through the
    per-node path, the same path hydration claims through.
    """

    def __init__(self) -> None:
        super().__init__(ServerDocument())

    def supports_html(self) -> bool:
        """Server rendering always uses per-node ops."""
        return False


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def _escape_text(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _escape_comment(text: str) -> str:
    return text.replace("--", "- -").replace(">", "&gt;")


def _option_selected(option: ServerElement, select: ServerElement | None) -> bool:
    if option.selected is not None:
        return bool(option.selected)
    if select is not None:
        value = option.value if option.value is not None else option.attributes.get("value")
        if value is None:
            value = "".join(str(n.nodeValue or "") for n in option._children() if n._is_text)
        if select.selectedValues is not None:
            return str(value) in {str(v) for v in select.selectedValues}
        if select.value is not None:
            return str(value) == str(select.value)
    return "selected" in option.attributes


def _attributes(el: ServerElement, select: ServerElement | None) -> str:
    attrs = dict(el.attributes)
    if el.style.decls:
        attrs["style"] = el.style.text()
    else:
        attrs.pop("style", None)
    tag = (el.tag or "").lower()
    if el.value is not None and tag not in ("textarea", "select", "option"):
        attrs["value"] = str(el.value)
    elif el.value is not None and tag == "option":
        attrs["value"] = str(el.value)
    if el.checked is not None:
        if el.checked:
            attrs["checked"] = ""
        else:
            attrs.pop("checked", None)
    if tag == "option":
        if _option_selected(el, select):
            attrs["selected"] = ""
        else:
            attrs.pop("selected", None)
    parts = []
    for name, value in attrs.items():
        parts.append(f" {name}" if value == "" else f' {name}="{escape(value, quote=True)}"')
    return "".join(parts)


def serialize_node(node: _Node, out: list[str], select: ServerElement | None = None, raw: bool = False) -> None:
    """Append the HTML for `node` to `out`."""
    if node._is_comment:
        out.append(f"<!--{_escape_comment(str(node.nodeValue or ''))}-->")
        return
    if node._is_text:
        text = str(node.nodeValue or "")
        out.append(text if raw else _escape_text(text))
        return
    assert isinstance(node, ServerElement)
    tag = node.tag or ""
    lower = tag.lower()
    out.append(f"<{tag}{_attributes(node, select)}>")
    if lower in VOID_ELEMENTS and node.namespaceURI is None:
        return
    if node.innerHTML is not None:
        out.append(node.innerHTML)
    elif lower == "textarea" and node.value is not None:
        text = str(node.value)
        out.append(("\n" if text.startswith("\n") else "") + _escape_text(text))
    else:
        start = len(out)
        inner_select = node if lower == "select" else select
        serialize_children(node, out, inner_select, raw=lower in _RAW_TEXT)
        if lower in _LEADING_NEWLINE and len(out) > start and out[start].startswith("\n"):
            out.insert(start, "\n")
    out.append(f"</{tag}>")


def serialize_children(node: _Node, out: list[str], select: ServerElement | None = None, raw: bool = False) -> None:
    """Append the HTML for every child of `node` to `out`."""
    child = node.firstChild
    while child is not None:
        serialize_node(child, out, select, raw)
        child = child.nextSibling


def inner_html(node: _Node) -> str:
    """Return the serialized HTML of `node`'s children."""
    out: list[str] = []
    serialize_children(node, out)
    return "".join(out)


def html_between(start: _Node, end: _Node) -> str:
    """Return the serialized HTML of the siblings strictly between two markers."""
    out: list[str] = []
    select = (
        start.parentNode if isinstance(start.parentNode, ServerElement) and start.parentNode.tag == "select" else None
    )
    node = start.nextSibling
    while node is not None and node is not end:
        serialize_node(node, out, select)
        node = node.nextSibling
    return "".join(out)
