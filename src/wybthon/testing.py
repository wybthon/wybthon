"""Render components in plain CPython and query them like a user would.

`wybthon.testing` mounts views into an in-memory DOM through the real
reconciler, kernel protocol, scheduler, and event delegation. Nothing is
mocked: the commands a test applies are exactly the commands the browser
kernel applies.

```python
from wybthon.testing import cleanup, fire, render


def test_counter():
    screen = render(Counter(label="Clicks"))
    fire.click(screen.get_by_role("button", name="+"))
    assert screen.get_by_text("Clicks: 1")
    cleanup()
```

Queries come in three forms, as in Testing Library:

- `get_by_*` returns the single match and raises when there are none or
  several;
- `query_by_*` returns the match or `None`;
- `get_all_by_*` returns every match (raising when there are none).

They search by visible text, ARIA role (with an optional accessible
name), label text, and `data-testid`. [`fire`][wybthon.testing.fire]
dispatches events through Wybthon's delegated handlers and flushes the
resulting updates, so assertions see the settled DOM.

Use `render` as a context manager to unmount automatically, or call
[`cleanup`][wybthon.testing.cleanup] at the end of each test (an
autouse pytest fixture is a convenient place).

Full-stack code tests the same way:

- [`connect_server`][wybthon.testing.connect_server] makes the
  components a test renders call their server functions the way the
  browser does, through the wire protocol and the server's argument
  validation, in-process.
- [`Client`][wybthon.testing.Client] sends HTTP requests to an ASGI
  app ([`wybthon.asgi.create_app`][wybthon.asgi.create_app]) without a
  network, for pages, form posts, and HTTP handlers.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from html.parser import HTMLParser
from typing import Any

from . import kernel
from ._html_rules import VOID_ELEMENTS
from .reactivity import _core

__all__ = [
    "render",
    "Screen",
    "fire",
    "cleanup",
    "TestNode",
    "TestDocument",
    "reactive_scope",
    "tick",
    "wait_for",
    "Client",
    "ClientResponse",
    "connect_server",
]


# ---------------------------------------------------------------------------
# In-memory DOM
# ---------------------------------------------------------------------------


class _ClassList:
    __slots__ = ("_names",)

    def __init__(self) -> None:
        self._names: set[str] = set()

    def add(self, name: str) -> None:
        self._names.add(name)

    def remove(self, name: str) -> None:
        self._names.discard(name)

    def contains(self, name: str) -> bool:
        return name in self._names


class _Style:
    __slots__ = ("_props",)

    def __init__(self) -> None:
        self._props: dict[str, str] = {}

    def setProperty(self, name: str, value: Any) -> None:
        self._props[name] = str(value)

    def removeProperty(self, name: str) -> None:
        self._props.pop(name, None)

    def getPropertyValue(self, name: str) -> str:
        return self._props.get(name, "")


class TestNode:
    """An in-memory DOM node: an element, a text node, or a comment.

    It implements the subset of the DOM the kernel protocol uses, plus
    the properties tests read (`text_content`, `attributes`, `value`,
    `checked`).
    """

    __test__ = False  # not a pytest test class

    active_element: TestNode | None = None

    def __init__(self, tag: str | None = None, text: str | None = None) -> None:
        self.tag = tag
        self.nodeValue = text
        self._is_text = text is not None
        self._is_comment = False
        self.parentNode: TestNode | None = None
        self.childNodes: list[TestNode] = []
        self.attributes: dict[str, str] = {}
        self.classList = _ClassList()
        self.style = _Style()
        self.value: Any = ""
        self.checked = False
        self.scrollTop = 0
        self.selectedValues: list[str] = []
        self._listeners: dict[str, set[Any]] = {}

    @property
    def nextSibling(self) -> TestNode | None:  # noqa: D102 - DOM API
        parent = self.parentNode
        if parent is None:
            return None
        siblings = parent.childNodes
        try:
            index = siblings.index(self)
        except ValueError:
            return None
        return siblings[index + 1] if index + 1 < len(siblings) else None

    @property
    def firstChild(self) -> TestNode | None:  # noqa: D102 - DOM API
        return self.childNodes[0] if self.childNodes else None

    def _detach(self, node: TestNode) -> None:
        if node.parentNode is not None:
            try:
                node.parentNode.childNodes.remove(node)
            except ValueError:
                pass

    def appendChild(self, node: TestNode) -> TestNode:  # noqa: D102 - DOM API
        self._detach(node)
        node.parentNode = self
        self.childNodes.append(node)
        return node

    def insertBefore(self, node: TestNode, anchor: TestNode | None) -> TestNode:  # noqa: D102 - DOM API
        self._detach(node)
        node.parentNode = self
        if anchor is None or anchor not in self.childNodes:
            self.childNodes.append(node)
        else:
            self.childNodes.insert(self.childNodes.index(anchor), node)
        return node

    def removeChild(self, node: TestNode) -> TestNode:  # noqa: D102 - DOM API
        try:
            self.childNodes.remove(node)
            node.parentNode = None
        except ValueError:
            pass
        return node

    def setAttribute(self, name: str, value: Any) -> None:  # noqa: D102 - DOM API
        self.attributes[name] = str(value)

    def getAttribute(self, name: str) -> str | None:  # noqa: D102 - DOM API
        return self.attributes.get(name)

    def removeAttribute(self, name: str) -> None:  # noqa: D102 - DOM API
        self.attributes.pop(name, None)

    def addEventListener(self, event_type: str, listener: Any, *_args: Any) -> None:  # noqa: D102 - DOM API
        self._listeners.setdefault(event_type, set()).add(listener)

    def removeEventListener(self, event_type: str, listener: Any, *_args: Any) -> None:  # noqa: D102 - DOM API
        self._listeners.get(event_type, set()).discard(listener)

    def focus(self) -> None:
        """Make this node the document's active element (no events are dispatched)."""
        TestNode.active_element = self

    def blur(self) -> None:
        """Clear the active element if it's this node."""
        if TestNode.active_element is self:
            TestNode.active_element = None

    def click(self) -> None:
        """Dispatch a click through Wybthon's delegated handlers (like `fire.click`)."""
        fire.click(self)

    @property
    def is_element(self) -> bool:
        """Whether this node is an element (not text or a comment)."""
        return self.tag is not None and not self._is_text and not self._is_comment

    @property
    def text_content(self) -> str:
        """The concatenated text of this node and its descendants (comments excluded)."""
        if self._is_comment:
            return ""
        if self._is_text:
            return str(self.nodeValue or "")
        return "".join(child.text_content for child in self.childNodes)

    def __repr__(self) -> str:
        if self._is_comment:
            return f"<!--{self.nodeValue}-->"
        if self._is_text:
            return f"TestNode(text={self.nodeValue!r})"
        return f"<{self.tag}>"


class _Parser(HTMLParser):
    """Builds `TestNode` trees from template HTML (backs `<template>.innerHTML`)."""

    def __init__(self, root: TestNode) -> None:
        super().__init__(convert_charrefs=True)
        self._stack = [root]

    def _element(self, tag: str, attrs: list[tuple[str, str | None]]) -> TestNode:
        node = TestNode(tag=tag)
        for name, value in attrs:
            value = "" if value is None else value
            node.setAttribute(name, value)
            if name == "class":
                for cls in value.split():
                    node.classList.add(cls)
            elif name == "style":
                for decl in value.split(";"):
                    if ":" in decl:
                        key, val = decl.split(":", 1)
                        node.style.setProperty(key.strip(), val.strip())
        self._stack[-1].appendChild(node)
        return node

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = self._element(tag, attrs)
        if tag not in VOID_ELEMENTS:
            self._stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._element(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if len(self._stack) > 1:
            self._stack.pop()

    def handle_data(self, data: str) -> None:
        if data:
            self._stack[-1].appendChild(TestNode(text=data))

    def handle_comment(self, data: str) -> None:
        node = TestNode(text=data)
        node._is_comment = True
        self._stack[-1].appendChild(node)


class _Template(TestNode):
    """`<template>`: parses `innerHTML` into a content fragment."""

    def __init__(self) -> None:
        super().__init__(tag="template")
        self.content = TestNode(tag="#fragment")

    @property
    def innerHTML(self) -> str:
        return ""

    @innerHTML.setter
    def innerHTML(self, html: str) -> None:
        self.content.childNodes = []
        if html:
            parser = _Parser(self.content)
            parser.feed(html)
            parser.close()


class TestDocument:
    """An in-memory `document` for the kernel's Python backend."""

    __test__ = False  # not a pytest test class

    def __init__(self) -> None:
        self.body = TestNode(tag="body")
        self._listeners: dict[str, set[Any]] = {}

    def createElement(self, tag: str) -> TestNode:  # noqa: D102 - DOM API
        return _Template() if tag == "template" else TestNode(tag=tag)

    def createElementNS(self, namespace: str, tag: str) -> TestNode:  # noqa: D102 - DOM API
        node = TestNode(tag=tag)
        node.attributes["xmlns"] = namespace
        return node

    def createTextNode(self, text: Any) -> TestNode:  # noqa: D102 - DOM API
        return TestNode(text=str(text))

    def createComment(self, text: Any = "") -> TestNode:  # noqa: D102 - DOM API
        node = TestNode(text=str(text))
        node._is_comment = True
        return node

    def addEventListener(self, event_type: str, listener: Any, *_args: Any) -> None:  # noqa: D102 - DOM API
        self._listeners.setdefault(event_type, set()).add(listener)

    def removeEventListener(self, event_type: str, listener: Any, *_args: Any) -> None:  # noqa: D102 - DOM API
        self._listeners.get(event_type, set()).discard(listener)

    def querySelector(self, selector: str) -> TestNode | None:  # noqa: D102 - DOM API
        if selector == "body":
            return self.body
        return _query(self.body, selector)

    def getElementById(self, element_id: str) -> TestNode | None:  # noqa: D102 - DOM API
        return _query(self.body, f"#{element_id}")


def _query(root: TestNode, selector: str) -> TestNode | None:
    """Minimal selector support: `#id`, `.class`, `tag`, and `[attr=value]`."""
    for node in _walk(root):
        if not node.is_element:
            continue
        if selector.startswith("#") and node.attributes.get("id") == selector[1:]:
            return node
        if selector.startswith(".") and selector[1:] in node.attributes.get("class", "").split():
            return node
        match = re.fullmatch(r"\[([\w-]+)(?:=[\"']?([^\"'\]]*)[\"']?)?\]", selector)
        if match and match.group(1) in node.attributes:
            if match.group(2) is None or node.attributes[match.group(1)] == match.group(2):
                return node
        if node.tag == selector:
            return node
    return None


def _walk(node: TestNode) -> Iterator[TestNode]:
    yield node
    for child in node.childNodes:
        yield from _walk(child)


def _serialize(node: TestNode, out: list[str]) -> None:
    from html import escape

    if node._is_comment:
        return
    if node._is_text:
        out.append(escape(str(node.nodeValue or ""), quote=False))
        return
    attrs = "".join(f' {name}="{escape(value)}"' for name, value in node.attributes.items())
    out.append(f"<{node.tag}{attrs}>")
    if node.tag not in VOID_ELEMENTS:
        for child in node.childNodes:
            _serialize(child, out)
        out.append(f"</{node.tag}>")


# ---------------------------------------------------------------------------
# Rendering and queries
# ---------------------------------------------------------------------------

_screens: list[Screen] = []


def _ensure_backend() -> Any:
    backend = kernel._backend
    if isinstance(backend, kernel.PythonBackend) and isinstance(backend._doc, TestDocument):
        return backend
    backend = kernel.PythonBackend(TestDocument())
    kernel.set_backend(backend)
    return backend


_IMPLICIT_ROLES = {
    "button": "button",
    "nav": "navigation",
    "main": "main",
    "header": "banner",
    "footer": "contentinfo",
    "aside": "complementary",
    "form": "form",
    "ul": "list",
    "ol": "list",
    "li": "listitem",
    "table": "table",
    "tr": "row",
    "td": "cell",
    "th": "columnheader",
    "textarea": "textbox",
    "select": "combobox",
    "option": "option",
    "dialog": "dialog",
    "img": "img",
    "progress": "progressbar",
    "h1": "heading",
    "h2": "heading",
    "h3": "heading",
    "h4": "heading",
    "h5": "heading",
    "h6": "heading",
}
_INPUT_ROLES = {"checkbox": "checkbox", "radio": "radio", "range": "slider", "button": "button", "submit": "button"}


def _role(node: TestNode) -> str | None:
    explicit = node.attributes.get("role")
    if explicit:
        return explicit
    tag = (node.tag or "").lower()
    if tag == "a":
        return "link" if "href" in node.attributes else None
    if tag == "input":
        return _INPUT_ROLES.get(node.attributes.get("type", "text"), "textbox")
    return _IMPLICIT_ROLES.get(tag)


def _accessible_name(node: TestNode) -> str:
    label = node.attributes.get("aria-label")
    if label:
        return label
    if (node.tag or "").lower() in ("input", "textarea", "select"):
        return node.attributes.get("placeholder", "") or node.attributes.get("value", "")
    return " ".join(node.text_content.split())


def _matches(text: str, expected: str | re.Pattern[str], exact: bool) -> bool:
    if isinstance(expected, re.Pattern):
        return expected.search(text) is not None
    normalized = " ".join(text.split())
    return normalized == expected if exact else expected.lower() in normalized.lower()


class Screen:
    """A rendered view and the queries that find nodes in it.

    Attributes:
        container: The `TestNode` the view is mounted into.
        root: The [`Root`][wybthon.Root] returned by `render`.
    """

    def __init__(self, root: Any, container: TestNode) -> None:
        self.root = root
        self.container = container

    def __enter__(self) -> Screen:
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.unmount()

    def unmount(self) -> None:
        """Dispose the view and release its container."""
        if self in _screens:
            _screens.remove(self)
        if not self.root._disposed:
            self.root.dispose()
            kernel.emit((kernel.OP_RELEASE, [self.root.node_id]))
            kernel.commit()

    def html(self) -> str:
        """The container's inner HTML, without Wybthon's comment markers."""
        out: list[str] = []
        for child in self.container.childNodes:
            _serialize(child, out)
        return "".join(out)

    def text(self) -> str:
        """The container's text content, with whitespace collapsed."""
        return " ".join(self.container.text_content.split())

    # -- generic --------------------------------------------------------------

    def _elements(self) -> Iterator[TestNode]:
        for node in _walk(self.container):
            if node is not self.container and node.is_element:
                yield node

    def _all(self, predicate: Callable[[TestNode], bool]) -> list[TestNode]:
        return [node for node in self._elements() if predicate(node)]

    @staticmethod
    def _one(found: list[TestNode], what: str) -> TestNode:
        if not found:
            raise LookupError(f"Unable to find an element {what}")
        if len(found) > 1:
            raise LookupError(f"Found {len(found)} elements {what}; use a get_all_by_* query")
        return found[0]

    @staticmethod
    def _some(found: list[TestNode], what: str) -> list[TestNode]:
        if not found:
            raise LookupError(f"Unable to find an element {what}")
        return found

    # -- text -------------------------------------------------------------------

    def _by_text(self, text: str | re.Pattern[str], exact: bool) -> list[TestNode]:
        # The deepest elements whose own text matches: a match's ancestors
        # contain the same text but aren't what the test means.
        found = [node for node in self._elements() if _matches(node.text_content, text, exact)]
        return [node for node in found if not any(child in found for child in _walk(node) if child is not node)]

    def get_by_text(self, text: str | re.Pattern[str], *, exact: bool = True) -> TestNode:
        """Return the one element whose text matches."""
        return self._one(self._by_text(text, exact), f"with text {text!r}")

    def query_by_text(self, text: str | re.Pattern[str], *, exact: bool = True) -> TestNode | None:
        """Return the element whose text matches, or `None`."""
        found = self._by_text(text, exact)
        return self._one(found, f"with text {text!r}") if found else None

    def get_all_by_text(self, text: str | re.Pattern[str], *, exact: bool = True) -> list[TestNode]:
        """Return every element whose text matches."""
        return self._some(self._by_text(text, exact), f"with text {text!r}")

    # -- role -------------------------------------------------------------------

    def _by_role(self, role: str, name: str | re.Pattern[str] | None) -> list[TestNode]:
        return self._all(
            lambda node: _role(node) == role and (name is None or _matches(_accessible_name(node), name, True))
        )

    def get_by_role(self, role: str, *, name: str | re.Pattern[str] | None = None) -> TestNode:
        """Return the one element with this ARIA role (and accessible name)."""
        return self._one(self._by_role(role, name), f"with role {role!r}" + (f" named {name!r}" if name else ""))

    def query_by_role(self, role: str, *, name: str | re.Pattern[str] | None = None) -> TestNode | None:
        """Return the element with this role (and name), or `None`."""
        found = self._by_role(role, name)
        return self._one(found, f"with role {role!r}") if found else None

    def get_all_by_role(self, role: str, *, name: str | re.Pattern[str] | None = None) -> list[TestNode]:
        """Return every element with this role (and name)."""
        return self._some(self._by_role(role, name), f"with role {role!r}")

    # -- label ------------------------------------------------------------------

    def _by_label(self, text: str | re.Pattern[str]) -> list[TestNode]:
        found: list[TestNode] = []
        for label in self._all(lambda node: node.tag == "label" and _matches(node.text_content, text, True)):
            target = label.attributes.get("for")
            if target:
                found.extend(node for node in self._elements() if node.attributes.get("id") == target)
            else:
                found.extend(
                    node for node in _walk(label) if node.is_element and node.tag in ("input", "select", "textarea")
                )
        found.extend(self._all(lambda node: _matches(node.attributes.get("aria-label", "\0"), text, True)))
        return list(dict.fromkeys(found))

    def get_by_label_text(self, text: str | re.Pattern[str]) -> TestNode:
        """Return the one form control labelled by `text`."""
        return self._one(self._by_label(text), f"labelled {text!r}")

    def query_by_label_text(self, text: str | re.Pattern[str]) -> TestNode | None:
        """Return the form control labelled by `text`, or `None`."""
        found = self._by_label(text)
        return self._one(found, f"labelled {text!r}") if found else None

    # -- test id ----------------------------------------------------------------

    def get_by_test_id(self, test_id: str) -> TestNode:
        """Return the one element with `data-testid` equal to `test_id`."""
        return self._one(self._all(lambda node: node.attributes.get("data-testid") == test_id), f"[{test_id}]")

    def query_by_test_id(self, test_id: str) -> TestNode | None:
        """Return the element with this `data-testid`, or `None`."""
        found = self._all(lambda node: node.attributes.get("data-testid") == test_id)
        return self._one(found, f"[{test_id}]") if found else None

    def get_all_by_test_id(self, test_id: str) -> list[TestNode]:
        """Return every element with this `data-testid`."""
        return self._some(self._all(lambda node: node.attributes.get("data-testid") == test_id), f"[{test_id}]")


def render(view: Any) -> Screen:
    """Mount `view` into a fresh in-memory container and flush it.

    Args:
        view: Anything `wybthon.render` accepts: a component call, an
            element, a list, or a reactive expression.

    Returns:
        A [`Screen`][wybthon.testing.Screen] for querying the result.
    """
    from .reconciler import render as render_view

    backend = _ensure_backend()
    container_id = kernel.alloc_id()
    kernel.emit((kernel.OP_CREATE_ELEMENT, container_id, "div"))
    kernel.commit()
    container = backend.get_node(container_id)
    backend._doc.body.appendChild(container)
    root = render_view(view, container_id)
    screen = Screen(root, container)
    _screens.append(screen)
    return screen


def cleanup() -> None:
    """Unmount every view rendered with [`render`][wybthon.testing.render] that's still mounted."""
    for screen in list(_screens):
        screen.unmount()


class _Fire:
    """Dispatch DOM events through Wybthon's delegated handlers, then flush."""

    def __call__(self, node: TestNode, event_type: str, **payload: Any) -> None:
        """Dispatch `event_type` at `node`; `payload` overrides event fields (`key`, `shift_key`, ...)."""
        backend = kernel._backend
        if not isinstance(backend, kernel.PythonBackend):
            raise RuntimeError("fire() needs a view rendered with wybthon.testing.render")
        fields = {_camel(name): value for name, value in payload.items()}
        backend.dispatch(event_type, node, payload=fields)
        _core.flush()

    def click(self, node: TestNode, **payload: Any) -> None:
        """Click `node`."""
        self(node, "click", **payload)

    def input(self, node: TestNode, value: str) -> None:
        """Type `value` into a text control (sets its value, then fires `input`)."""
        node.value = value
        self(node, "input")

    def change(self, node: TestNode, value: Any = None, *, checked: bool | None = None) -> None:
        """Change a control's value or checked state, then fire `change`."""
        if value is not None:
            node.value = value
        if checked is not None:
            node.checked = checked
        self(node, "change")

    def submit(self, node: TestNode) -> None:
        """Submit a form."""
        self(node, "submit")

    def key_down(self, node: TestNode, key: str, **payload: Any) -> None:
        """Press `key` on `node`."""
        self(node, "keydown", key=key, **payload)

    def focus(self, node: TestNode) -> None:
        """Focus `node`."""
        self(node, "focus")

    def blur(self, node: TestNode) -> None:
        """Blur `node`."""
        self(node, "blur")


def _camel(name: str) -> str:
    head, *rest = name.split("_")
    return head + "".join(part.title() for part in rest)


fire = _Fire()
"""Dispatch events: `fire.click(node)`, `fire.input(node, "text")`, `fire(node, "dblclick")`."""


# ---------------------------------------------------------------------------
# Reactive helpers
# ---------------------------------------------------------------------------


@contextmanager
def reactive_scope() -> Iterator[_core.Owner]:
    """Own test computations and dispose them deterministically at scope exit."""
    owner = _core.Owner()
    previous = _core._current_owner
    _core._current_owner = owner
    try:
        yield owner
    finally:
        _core._current_owner = previous
        owner.dispose()
        _core.flush()


async def tick(rounds: int = 2) -> None:
    """Drain ready asyncio continuations and flush reactive work."""
    if rounds < 1:
        raise ValueError("rounds must be positive")
    for _ in range(rounds):
        await asyncio.sleep(0)
        _core.flush()


async def wait_for(predicate: Callable[[], bool], *, timeout: float = 1, interval: float = 0.001) -> None:
    """Wait for an observable condition, raising TimeoutError on failure."""
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(interval)
            _core.flush()


# ---------------------------------------------------------------------------
# Server functions and ASGI apps
# ---------------------------------------------------------------------------


class ClientResponse:
    """A response a [`Client`][wybthon.testing.Client] received.

    Attributes:
        status: The status code.
        headers: Header values by lowercase name (repeated headers joined
            with `, `, except `set-cookie`, which is in `cookies`).
        cookies: Every `set-cookie` value.
        body: The body.
    """

    __slots__ = ("status", "headers", "cookies", "body")

    def __init__(self, status: int, headers: dict[str, str], cookies: list[str], body: bytes) -> None:
        self.status = status
        self.headers = headers
        self.cookies = cookies
        self.body = body

    @property
    def text(self) -> str:
        """The body as text."""
        return self.body.decode("utf-8", "replace")

    def json(self) -> Any:
        """The body parsed as JSON."""
        import json

        return json.loads(self.body)

    def __repr__(self) -> str:
        return f"ClientResponse({self.status})"


class Client:
    """Send requests to an ASGI app in-process; cookies persist between requests.

    ```python
    from wybthon.asgi import create_app
    from wybthon.testing import Client

    def test_home_page():
        client = Client(create_app("tests/fixture_app"))
        page = client.get("/")
        assert page.status == 200 and "Todos" in page.text
    ```
    """

    def __init__(self, app: Any, *, host: str = "testserver") -> None:
        self.app = app
        self.host = host
        self.cookies: dict[str, str] = {}

    async def request_async(
        self, method: str, path: str, *, body: bytes = b"", headers: dict[str, str] | None = None
    ) -> ClientResponse:
        """Send a request from a running event loop."""
        target, _, query = path.partition("?")
        merged = {"host": self.host, **{key.lower(): value for key, value in (headers or {}).items()}}
        if self.cookies and "cookie" not in merged:
            merged["cookie"] = "; ".join(f"{name}={value}" for name, value in self.cookies.items())
        if body and "content-length" not in merged:
            merged["content-length"] = str(len(body))
        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": method.upper(),
            "scheme": "http",
            "path": target,
            "raw_path": target.encode(),
            "query_string": query.encode(),
            "headers": [(name.encode("latin-1"), value.encode("latin-1")) for name, value in merged.items()],
        }
        delivered = False

        async def receive() -> dict[str, Any]:
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": body, "more_body": False}
            return {"type": "http.disconnect"}

        status = 0
        response_headers: dict[str, str] = {}
        cookies: list[str] = []
        chunks: list[bytes] = []

        async def send(message: dict[str, Any]) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                for raw_name, raw_value in message.get("headers", []):
                    name, value = raw_name.decode("latin-1").lower(), raw_value.decode("latin-1")
                    if name == "set-cookie":
                        cookies.append(value)
                    else:
                        response_headers[name] = (
                            f"{response_headers[name]}, {value}" if name in response_headers else value
                        )
            elif message["type"] == "http.response.body":
                chunks.append(message.get("body", b""))

        await self.app(scope, receive, send)
        for cookie in cookies:
            pair = cookie.split(";", 1)[0]
            name, _, value = pair.partition("=")
            if "max-age=0" in cookie.lower().replace(" ", ""):
                self.cookies.pop(name.strip(), None)
            else:
                self.cookies[name.strip()] = value.strip()
        return ClientResponse(status, response_headers, cookies, b"".join(chunks))

    def request(
        self, method: str, path: str, *, body: bytes = b"", headers: dict[str, str] | None = None
    ) -> ClientResponse:
        """Send a request and wait for the whole response."""
        return asyncio.run(self.request_async(method, path, body=body, headers=headers))

    def get(self, path: str, *, headers: dict[str, str] | None = None) -> ClientResponse:
        """`GET path`, as a browser loading a page would (it accepts HTML)."""
        return self.request("GET", path, headers={"accept": "text/html", **(headers or {})})

    def post_form(
        self, path: str, fields: dict[str, str] | list[tuple[str, str]], *, referer: str = "/"
    ) -> ClientResponse:
        """Post a form the way a browser without JavaScript does."""
        from urllib.parse import urlencode

        return self.request(
            "POST",
            path,
            body=urlencode(fields).encode(),
            headers={
                "content-type": "application/x-www-form-urlencoded",
                "origin": f"http://{self.host}",
                "referer": f"http://{self.host}{referer}",
            },
        )


@contextmanager
def connect_server(app: Any = None, *, base: str = "/") -> Iterator[None]:
    """Make server function calls inside the block cross the wire, as they would in the browser.

    With no `app`, each call is handled in-process by the server-side
    handler: arguments are encoded, validated against the function's
    annotations, and the result decoded, exactly as over HTTP. With an
    ASGI `app` (such as `wybthon.asgi.create_app(...)`), each call is a
    request to it.

    ```python
    def test_add_todo():
        with connect_server(), render(TodoPage()) as screen:
            fire.input(screen.get_by_role("textbox"), "Write tests")
            fire.submit(screen.get_by_role("form"))
            ...
    ```
    """
    from . import server_functions
    from .request import RequestEvent

    client = Client(app) if app is not None else None

    async def transport(method: str, url: str, headers: dict[str, str], body: Any) -> tuple[int, dict[str, str], bytes]:
        # A request never completes synchronously in the browser.
        await asyncio.sleep(0)
        if client is not None:
            response = await client.request_async(method, url, body=body or b"", headers=headers)
            return response.status, response.headers, response.body
        path, _, query = url.partition("?")
        fn_id = path.split(server_functions.FN_PATH, 1)[1]
        event = RequestEvent(url=url, method=method, headers=headers)
        status, response_headers, data, _fn, _outcome = await server_functions.handle(
            event, fn_id, method, query, headers, body or b""
        )
        return status, response_headers, data

    with server_functions._remote_calls(transport, base=base):
        yield
