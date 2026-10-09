"""HTML templates written as t-strings, compiled once per literal.

[`html`][wybthon.html] turns a [PEP 750](https://peps.python.org/pep-0750/)
template string into a node:

```python
from wybthon import component, create_signal, html


@component
def Counter():
    count, set_count = create_signal(0)

    def increment():
        set_count(lambda n: n + 1)

    return html(t\"\"\"
      <div class="counter">
        <p>Count: {count}</p>
        <button onclick={increment}>+</button>
      </div>
    \"\"\")
```

A t-string literal's static strings are a constant of the code that
contains it: every evaluation of the same literal yields the *same*
`strings` tuple. Wybthon keys a compiled template on that identity, so a
literal is parsed, validated, and compiled once, and every later call
only supplies the interpolated values. (Python doesn't allow a bare
`lambda` inside an interpolation; wrap it in parentheses or give it a
name.) This is the runtime counterpart of
Solid's JSX compiler (and of its buildless `html` tagged template):

- the static markup becomes one native `<template>` the kernel clones
  with a single command per instance, with no VNode tree for its static
  parts;
- each interpolation becomes a *slot* at a known node offset: a child, an
  attribute or part of one, an event handler, a ref, a spread of props,
  or a component tag;
- when a reactive hole returns a template from the same literal again,
  the mounted instance is patched slot by slot.

Interpolations behave exactly like the element helpers'
([`wybthon.elements`][wybthon.elements]) children and props: an
accessor or zero-argument function becomes a reactive binding, anything
else is applied once. Server rendering, hydration, and SVG expand the
template into ordinary VNodes, so their output matches the helpers'.

See the [templates guide](https://wybthon.com/concepts/templates/).
"""

from __future__ import annotations

import html as _html_entities
import re
from collections.abc import Callable
from string.templatelib import Interpolation, Template
from typing import Any

from . import diagnostics, kernel
from . import events as _events
from ._dom_props import (
    _FRESH,
    _apply_single_prop,
    _bind_reactive_prop,
    apply_initial_props,
    apply_props,
    attach_ref,
    binding_value,
    detach_ref,
    remove_bindings_for,
)
from ._html_rules import (
    ALLOWED_CHILDREN,
    FOREIGN_ELEMENTS,
    HEADINGS,
    LEADING_NEWLINE_ELEMENTS,
    NO_NESTED_CHILD,
    NO_NESTED_DESCENDANT,
    NO_TEXT_CONTENT,
    P_CLOSERS,
    RAW_CONTENT_ELEMENTS,
    VOID_ELEMENTS,
)
from .reactivity._core import is_accessor
from .vnode import VNode, flatten_children, render_template, to_text_vnode

__all__ = ["html", "TemplateError"]


class TemplateError(ValueError):
    """Raised when a template's markup is malformed or would be rewritten by the HTML parser."""


# ---------------------------------------------------------------------------
# Parse tree
# ---------------------------------------------------------------------------

# Attribute kinds in the parse tree.
_A_STATIC = 0  # (kind, name, value: str | True)
_A_VALUE = 1  # (kind, name, index)
_A_PARTS = 2  # (kind, name, parts: tuple[str | int, ...])
_A_SPREAD = 3  # (kind, index)


# Elements whose content a template may only write as static text.
_STATIC_CONTENT = RAW_CONTENT_ELEMENTS - {"iframe", "template"}
# Elements whose content isn't child nodes at all.
_UNSUPPORTED = frozenset({"iframe", "template"})


class _Element:
    __slots__ = ("tag", "attrs", "children")

    def __init__(self, tag: str, attrs: list[tuple[Any, ...]]) -> None:
        self.tag = tag
        self.attrs = attrs
        self.children: list[Any] = []


class _Component:
    __slots__ = ("index", "attrs", "children")

    def __init__(self, index: int, attrs: list[tuple[Any, ...]]) -> None:
        self.index = index
        self.attrs = attrs
        self.children: list[Any] = []


class _Slot:
    """A child interpolation."""

    __slots__ = ("index",)

    def __init__(self, index: int) -> None:
        self.index = index


# Interpolation markers in the joined source: private-use characters that
# can't appear in a template's static text (checked before parsing).
_OPEN = ""
_CLOSE = ""
_MARKER = re.compile(_OPEN + r"(\d+)" + _CLOSE)
_TAG_NAME = re.compile(r"[A-Za-z][A-Za-z0-9:._-]*")
_ATTR_NAME = re.compile(r"[^\s\"'<>/=" + _OPEN + _CLOSE + r"]+")
_UNQUOTED = re.compile(r"[^\s\"'=<>`]+")
_NEWLINES = re.compile(r"\r\n|\n|\r")


def _source(strings: tuple[str, ...]) -> str:
    """Rebuild the template's source for error messages, with `{...}` for slots."""
    return "{...}".join(strings)


class _Parser:
    def __init__(self, strings: tuple[str, ...]) -> None:
        for text in strings:
            if _OPEN in text or _CLOSE in text:
                raise TemplateError("Templates can't contain the characters U+E000 or U+E001")
        self.strings = strings
        self.src = "".join(
            text + (f"{_OPEN}{index}{_CLOSE}" if index < len(strings) - 1 else "") for index, text in enumerate(strings)
        )
        self.pos = 0

    def error(self, message: str) -> TemplateError:
        return TemplateError(f"{message}\n  in template: t{_source(self.strings)!r}")

    def marker_at(self, pos: int) -> re.Match[str] | None:
        return _MARKER.match(self.src, pos)

    def parse(self) -> list[Any]:
        nodes = self.nodes(None)
        if self.pos < len(self.src):  # pragma: no cover - nodes() consumes everything at top level
            raise self.error("Unexpected content")
        return nodes

    def nodes(self, parent: _Element | _Component | None) -> list[Any]:
        """Parse children until the closing tag of `parent` (or the end)."""
        src = self.src
        out: list[Any] = []
        text: list[str] = []

        def flush_text() -> None:
            if text:
                out.append(("text", "".join(text)))
                text.clear()

        while self.pos < len(src):
            ch = src[self.pos]
            if ch == _OPEN:
                m = self.marker_at(self.pos)
                assert m is not None
                flush_text()
                out.append(_Slot(int(m.group(1))))
                self.pos = m.end()
                continue
            if ch != "<":
                nxt = len(src)
                for stop in ("<", _OPEN):
                    found = src.find(stop, self.pos)
                    if found != -1 and found < nxt:
                        nxt = found
                text.append(src[self.pos : nxt])
                self.pos = nxt
                continue
            if src.startswith("<!--", self.pos):
                end = src.find("-->", self.pos + 4)
                if end == -1:
                    raise self.error("Unclosed comment")
                self.pos = end + 3
                continue
            if src.startswith("</", self.pos):
                flush_text()
                self.close_tag(parent)
                return out
            if src.startswith("<!", self.pos) or src.startswith("<?", self.pos):
                raise self.error("Doctypes and processing instructions aren't allowed in templates")
            flush_text()
            out.append(self.open_tag())
        if parent is not None:
            raise self.error(f"Unclosed tag <{self.tag_label(parent)}>")
        flush_text()
        return out

    def tag_label(self, node: _Element | _Component) -> str:
        return node.tag if isinstance(node, _Element) else "{...}"

    def close_tag(self, parent: _Element | _Component | None) -> None:
        src = self.src
        start = self.pos
        self.pos += 2
        m = self.marker_at(self.pos)
        if m is not None:
            name: str | int = int(m.group(1))
            self.pos = m.end()
        else:
            tm = _TAG_NAME.match(src, self.pos)
            if tm is None:
                raise self.error(f"Malformed closing tag at {src[start : start + 12]!r}")
            name = tm.group(0)
            self.pos = tm.end()
        while self.pos < len(src) and src[self.pos].isspace():
            self.pos += 1
        if self.pos >= len(src) or src[self.pos] != ">":
            raise self.error("Malformed closing tag")
        self.pos += 1
        if parent is None:
            raise self.error(f"Unexpected closing tag </{name if isinstance(name, str) else '{...}'}>")
        if isinstance(parent, _Element):
            if not isinstance(name, str) or name.lower() != parent.tag.lower():
                label = name if isinstance(name, str) else "{...}"
                raise self.error(f"Closing tag </{label}> doesn't match <{parent.tag}>")
        elif not isinstance(name, int):
            raise self.error(f"Closing tag </{name}> doesn't match a component tag; close it with </{{...}}>")

    def open_tag(self) -> _Element | _Component:
        src = self.src
        self.pos += 1
        m = self.marker_at(self.pos)
        node: _Element | _Component
        if m is not None:
            node = _Component(int(m.group(1)), [])
            self.pos = m.end()
        else:
            tm = _TAG_NAME.match(src, self.pos)
            if tm is None:
                raise self.error("A '<' must start a tag; write &lt; for a literal less-than sign")
            node = _Element(tm.group(0), [])
            if node.tag.lower() in _UNSUPPORTED:
                raise self.error(f"<{node.tag}> isn't supported in templates; create it with element()")
            self.pos = tm.end()
        self_closing = self.attributes(node)
        if isinstance(node, _Element):
            lower = node.tag.lower()
            if lower in VOID_ELEMENTS or self_closing:
                return node
            if lower in _STATIC_CONTENT:
                close = re.compile(r"</" + re.escape(lower) + r"\s*>", re.IGNORECASE)
                end = close.search(src, self.pos)
                if end is None:
                    raise self.error(f"Unclosed tag <{node.tag}>")
                body = src[self.pos : end.start()]
                if _OPEN in body:
                    raise self.error(f"<{node.tag}> takes static text only; interpolate its attributes instead")
                if body:
                    node.children.append(("raw", body))
                self.pos = end.end()
                return node
        elif self_closing:
            return node
        node.children = self.nodes(node)
        return node

    def attributes(self, node: _Element | _Component) -> bool:
        """Parse attributes up to `>` or `/>`; returns whether the tag self-closes."""
        src = self.src
        attrs = node.attrs
        while True:
            while self.pos < len(src) and src[self.pos].isspace():
                self.pos += 1
            if self.pos >= len(src):
                raise self.error("Unclosed tag")
            ch = src[self.pos]
            if ch == ">":
                self.pos += 1
                return False
            if src.startswith("/>", self.pos):
                self.pos += 2
                return True
            m = self.marker_at(self.pos)
            if m is not None:
                attrs.append((_A_SPREAD, int(m.group(1))))
                self.pos = m.end()
                continue
            nm = _ATTR_NAME.match(src, self.pos)
            if nm is None:
                raise self.error(f"Malformed attribute at {src[self.pos : self.pos + 12]!r}")
            name = nm.group(0)
            self.pos = nm.end()
            while self.pos < len(src) and src[self.pos].isspace():
                self.pos += 1
            if self.pos >= len(src) or src[self.pos] != "=":
                attrs.append((_A_STATIC, name, True))
                continue
            self.pos += 1
            while self.pos < len(src) and src[self.pos].isspace():
                self.pos += 1
            m = self.marker_at(self.pos)
            if m is not None:
                attrs.append((_A_VALUE, name, int(m.group(1))))
                self.pos = m.end()
                continue
            quote = src[self.pos] if self.pos < len(src) else ""
            if quote in ("'", '"'):
                end = src.find(quote, self.pos + 1)
                if end == -1:
                    raise self.error(f"Unclosed attribute value for {name!r}")
                raw = src[self.pos + 1 : end]
                self.pos = end + 1
            else:
                um = _UNQUOTED.match(src, self.pos)
                if um is None:
                    raise self.error(f"Missing value for attribute {name!r}")
                raw = um.group(0)
                self.pos = um.end()
            if _OPEN not in raw:
                attrs.append((_A_STATIC, name, _html_entities.unescape(raw)))
                continue
            parts: list[str | int] = []
            last = 0
            for pm in _MARKER.finditer(raw):
                if pm.start() > last:
                    parts.append(_html_entities.unescape(raw[last : pm.start()]))
                parts.append(int(pm.group(1)))
                last = pm.end()
            if last < len(raw):
                parts.append(_html_entities.unescape(raw[last:]))
            if len(parts) == 1 and isinstance(parts[0], int):
                attrs.append((_A_VALUE, name, parts[0]))
            else:
                attrs.append((_A_PARTS, name, tuple(parts)))


def _clean_text(text: str) -> str:
    """Apply JSX whitespace rules to one run of static text."""
    lines = _NEWLINES.split(text)
    if len(lines) == 1:
        return text
    last_non_empty = -1
    for index, line in enumerate(lines):
        if line.strip(" \t"):
            last_non_empty = index
    out: list[str] = []
    for index, line in enumerate(lines):
        trimmed = line.replace("\t", " ")
        if index:
            trimmed = trimmed.lstrip(" ")
        if index < len(lines) - 1:
            trimmed = trimmed.rstrip(" ")
        if trimmed:
            if index != last_non_empty:
                trimmed += " "
            out.append(trimmed)
    return "".join(out)


def _normalize(nodes: list[Any], parent: _Element | None, parser: _Parser, ancestors: frozenset[str]) -> list[Any]:
    """Clean whitespace, decode entities, merge text, and validate content models."""
    lower = parent.tag.lower() if parent is not None else None
    verbatim = lower == "pre" or "pre" in ancestors
    out: list[Any] = []
    for node in nodes:
        if isinstance(node, tuple):
            kind, raw = node
            if kind == "raw":
                text = raw
            else:
                text = raw if verbatim else _clean_text(raw)
                text = _html_entities.unescape(text)
            if not text:
                continue
            if lower in NO_TEXT_CONTENT:
                if text.strip():
                    raise parser.error(f"<{parent.tag}> can't contain text")
                continue
            if out and isinstance(out[-1], str):
                out[-1] += text
            else:
                out.append(text)
            continue
        if isinstance(node, _Element):
            tag = node.tag.lower()
            if lower is not None:
                allowed = ALLOWED_CHILDREN.get(lower)
                if allowed is not None and tag not in allowed:
                    hint = " (add a <tbody>)" if lower == "table" and tag == "tr" else ""
                    raise parser.error(f"<{node.tag}> can't be a child of <{parent.tag}>{hint}")
                if lower == "p" and tag in P_CLOSERS:
                    raise parser.error(f"<{node.tag}> can't be inside <p>; the HTML parser would close the <p>")
                if tag in NO_NESTED_CHILD and (tag == lower or (tag in HEADINGS and lower in HEADINGS)):
                    raise parser.error(f"<{node.tag}> can't be a direct child of <{parent.tag}>")
            if tag in NO_NESTED_DESCENDANT and tag in ancestors:
                raise parser.error(f"<{node.tag}> can't be nested inside another <{node.tag}>")
            node.children = _normalize(node.children, node, parser, ancestors | {tag})
        elif isinstance(node, _Component):
            node.children = _normalize(node.children, None, parser, ancestors)
        out.append(node)
    return out


# ---------------------------------------------------------------------------
# Name normalization
# ---------------------------------------------------------------------------


def _event_prop(name: str) -> str | None:
    """Map `onclick`, `onClick`, `on:click`, or `on_click` to the helper prop name (`on_click`)."""
    if len(name) <= 2 or name[:2].lower() != "on":
        return None
    rest = name[2:].lstrip(":_")
    if not rest:
        return None
    capture = ""
    if len(rest) > 7 and rest[-7:].lower() == "capture":
        rest = rest[:-7].rstrip("_:")
        capture = "_capture"
    return "on_" + rest.lower() + capture


def _component_prop(name: str, parser: _Parser) -> str:
    prop = name.replace("-", "_")
    if not prop.isidentifier():
        raise parser.error(f"{name!r} isn't a valid component prop name")
    return prop


# ---------------------------------------------------------------------------
# Compilation
# ---------------------------------------------------------------------------

# Slot kinds in a compiled element's plan.
_S_PROP = 0  # (kind, offset, index, name)
_S_PARTS = 1  # (kind, offset, parts, name)
_S_EVENT = 2  # (kind, offset, index, name, key, delegated)
_S_REF = 3  # (kind, offset, index)
_S_SPREAD = 4  # (kind, offset, index)
_S_CHILD = 5  # (kind, offset, index, parent offset, text slot or -1)
_S_COMPONENT = 6  # (kind, offset, component node, parent offset)


class _Compiled:
    """A compiled single-element template: skeleton, slot plan, and expansion tree.

    The attributes the kernel reads (`html`, `count`, `texts`, `listens`,
    `tpl`) match RFC 0002's shapes, so registration and cloning share the
    kernel protocol.
    """

    __slots__ = (
        "root",
        "html",
        "count",
        "texts",
        "listens",
        "tpl",
        "plan",
        "handlers",
        "refs",
        "spreads",
        "foreign",
        "strings",
        "mount",
    )

    def __init__(self, root: _Element, strings: tuple[str, ...]) -> None:
        self.root = root
        self.strings = strings
        self.html = ""
        self.count = 0
        self.texts: list[int] = []
        self.listens: list[list[Any]] = []
        self.tpl = 0
        self.plan: tuple[tuple[Any, ...], ...] = ()
        self.handlers: tuple[int, ...] = ()
        self.refs: tuple[int, ...] = ()
        self.spreads: tuple[int, ...] = ()
        self.foreign = False
        # Generated on first mount (see ``_generate``).
        self.mount: Callable[[VNode, int, int | None], None] = _generate_and_mount


class _Builder:
    def __init__(self, compiled: _Compiled, parser: _Parser) -> None:
        self.c = compiled
        self.parser = parser
        self.out: list[str] = []
        self.count = 0
        self.plan: list[tuple[Any, ...]] = []
        self.handlers: list[int] = []
        self.refs: list[int] = []
        self.spreads: list[int] = []

    def element(self, node: _Element) -> None:
        offset = self.count
        self.count += 1
        tag = node.tag
        lower = tag.lower()
        if lower in FOREIGN_ELEMENTS:
            self.c.foreign = True
        out = self.out
        out.append("<" + tag)
        for attr in node.attrs:
            kind = attr[0]
            if kind == _A_STATIC:
                _, name, value = attr
                if value is True:
                    out.append(" " + name)
                else:
                    out.append(f' {name}="{_html_entities.escape(value, quote=True)}"')
            elif kind == _A_SPREAD:
                self.plan.append((_S_SPREAD, offset, attr[1]))
                self.spreads.append(offset)
            else:
                _, name, value = attr
                event = _event_prop(name)
                if event is not None:
                    if kind == _A_PARTS:
                        raise self.parser.error(f"Event handler {name!r} must be a single interpolation")
                    key = _events._event_key(event)
                    delegated = not key.endswith(":capture") and key not in _events.NON_BUBBLING
                    if delegated:
                        self.c.listens.append([offset, key])
                    self.plan.append((_S_EVENT, offset, value, event, key, delegated))
                    self.handlers.append(offset)
                elif name == "ref":
                    if kind == _A_PARTS:
                        raise self.parser.error("ref must be a single interpolation")
                    self.plan.append((_S_REF, offset, value))
                    self.refs.append(offset)
                elif name == "key" or name == "children":
                    continue
                elif kind == _A_PARTS:
                    self.plan.append((_S_PARTS, offset, value, name))
                else:
                    self.plan.append((_S_PROP, offset, value, name))
        out.append(">")
        if lower in VOID_ELEMENTS:
            if node.children:  # pragma: no cover - the parser never gives void elements children
                raise self.parser.error(f"<{tag}> can't have children")
            return
        children = node.children
        raw = lower in _STATIC_CONTENT
        no_text = lower in NO_TEXT_CONTENT
        prev_text = False
        for index, child in enumerate(children):
            if isinstance(child, str):
                if index == 0 and lower in LEADING_NEWLINE_ELEMENTS and child.startswith("\n"):
                    # The parser drops a newline right after the start tag.
                    out.append("\n")
                out.append(child if raw else _html_entities.escape(child, quote=False))
                self.count += 1
                prev_text = True
            elif isinstance(child, _Element):
                self.element(child)
                prev_text = False
            elif isinstance(child, _Component):
                self.plan.append((_S_COMPONENT, self.count, child, offset))
                self.count += 1
                out.append("<!---->")
                prev_text = False
            else:
                nxt = children[index + 1] if index + 1 < len(children) else None
                text_anchor = not no_text and not prev_text and not isinstance(nxt, (str, _Slot))
                slot = -1
                if text_anchor:
                    slot = len(self.c.texts)
                    self.c.texts.append(self.count)
                    out.append(" ")
                else:
                    out.append("<!---->")
                self.plan.append((_S_CHILD, self.count, child.index, offset, slot))
                self.count += 1
                prev_text = text_anchor
        out.append(f"</{tag}>")

    def finish(self) -> None:
        c = self.c
        c.html = "".join(self.out)
        c.count = self.count
        c.plan = tuple(self.plan)
        c.handlers = tuple(self.handlers)
        c.refs = tuple(self.refs)
        c.spreads = tuple(self.spreads)


# A compiled template: how `html()` turns values into a node.
#   ("element", _Compiled)            one element root (clone path)
#   ("parts", tuple[part, ...])       several roots, text, or slots (a fragment)
# Parts: str (static text), int (child slot), _Compiled, or _Component.
_Program = tuple[str, Any]


def _compile_element(node: _Element, parser: _Parser) -> _Compiled:
    compiled = _Compiled(node, parser.strings)
    builder = _Builder(compiled, parser)
    builder.element(node)
    builder.finish()
    return compiled


def _compile_nodes(nodes: list[Any], parser: _Parser) -> _Program:
    elements = [n for n in nodes if not (isinstance(n, str) and not n.strip())]
    if len(elements) == 1 and isinstance(elements[0], _Element):
        return ("element", _compile_element(elements[0], parser))
    parts: list[Any] = []
    for node in nodes:
        if isinstance(node, str):
            parts.append(node)
        elif isinstance(node, _Slot):
            parts.append(node.index)
        elif isinstance(node, _Element):
            parts.append(_compile_element(node, parser))
        else:
            _compile_component_children(node, parser)
            parts.append(node)
    return ("parts", tuple(parts))


def _compile_component_children(node: _Component, parser: _Parser) -> None:
    for attr in node.attrs:
        if attr[0] in (_A_STATIC, _A_VALUE, _A_PARTS):
            _component_prop(attr[1], parser)
    # Children compile once and are stored in place of the parsed list.
    node.children = [_compile_nodes(node.children, parser)] if node.children else []


def _walk_components(node: _Element, parser: _Parser) -> None:
    for child in node.children:
        if isinstance(child, _Element):
            _walk_components(child, parser)
        elif isinstance(child, _Component):
            _compile_component_children(child, parser)


class _Entry:
    __slots__ = ("strings", "program", "formats")

    def __init__(self, strings: tuple[str, ...], program: _Program, formats: tuple[int, ...]) -> None:
        self.strings = strings
        self.program = program
        self.formats = formats


# Keyed by ``id(strings)``; the entry holds the tuple, so the id can't be reused
# while cached. Literals are code, so the cache is bounded by the program.
_by_identity: dict[int, _Entry] = {}
# Structural fallback for templates whose strings aren't a literal's constant.
_by_value: dict[tuple[str, ...], _Entry] = {}
_VALUE_CACHE_MAX = 1024


def _compile(template: Template) -> _Entry:
    strings = template.strings
    entry = _by_value.get(strings)
    if entry is None:
        parser = _Parser(strings)
        nodes = _normalize(parser.parse(), None, parser, frozenset())
        program = _compile_nodes(nodes, parser)
        if program[0] == "element":
            _walk_components(program[1].root, parser)
        else:
            for part in program[1]:
                if isinstance(part, _Compiled):
                    _walk_components(part.root, parser)
        formats = tuple(
            index for index, item in enumerate(template.interpolations) if item.conversion or item.format_spec
        )
        entry = _Entry(strings, program, formats)
        if len(_by_value) >= _VALUE_CACHE_MAX:
            _by_value.pop(next(iter(_by_value)))
        _by_value[strings] = entry
    _by_identity[id(strings)] = entry
    return entry


def _format_value(item: Interpolation) -> Any:
    value = item.value

    def text(v: Any) -> str:
        if item.conversion == "r":
            v = repr(v)
        elif item.conversion == "s":
            v = str(v)
        elif item.conversion == "a":
            v = ascii(v)
        return "" if v is None else format(v, item.format_spec)

    if is_accessor(value):
        return lambda: text(value())
    return text(value)


def html(template: Template) -> VNode:
    """Render a t-string template to a node.

    The template is HTML with interpolations. Each literal is compiled
    once (see the module docs); later calls only supply values.

    Interpolation positions:

    - **Child** (`<p>{value}</p>`): text, a node, a list, `None`, or a
      reactive expression (an accessor or zero-argument function), which
      becomes a hole.
    - **Attribute** (`<a href={url}>`): a value applied once, or a
      reactive expression bound to that attribute.
    - **Part of an attribute** (`class="card card-{kind}"`): the parts
      form one string, re-rendered together when any reactive part
      changes.
    - **Event** (`onclick={handler}`, `onClick`, or `on:click`): a
      delegated handler, taking the event or no arguments.
    - **Spread** (`<input {attrs}>`): a mapping of props.
    - **Component tag** (`<{Card} title="Hi">...</{Card}>` or
      `<{Card} />`): calls the component with the attributes as keyword
      props and the content as `children`.

    Attribute names are HTML names (`class`, `for`, `aria-label`). Text
    follows JSX's whitespace rules: text spanning lines is trimmed line by
    line and joined with spaces, and whitespace-only text containing a
    newline is dropped. Several top-level nodes make a fragment.

    Args:
        template: A t-string.

    Returns:
        A node to place in the tree or return from a component.

    Raises:
        TemplateError: The markup is malformed, or the HTML parser would
            rewrite it (for example `<tr>` directly inside `<table>`).

    Example:
        ```python
        html(t'<li class={(lambda: "done" if done() else "")}>{title}</li>')
        ```
    """
    if type(template) is not Template:
        raise TypeError(f"html() takes a t-string, got {type(template).__name__}")
    strings = template.strings
    entry = _by_identity.get(id(strings))
    if entry is None or entry.strings is not strings:
        entry = _compile(template)
    values: tuple[Any, ...] = template.values
    if entry.formats:
        items = template.interpolations
        mutable = list(values)
        for index in entry.formats:
            mutable[index] = _format_value(items[index])
        values = tuple(mutable)
    kind, data = entry.program
    if kind == "element":
        return VNode("_tpl", data, values)  # type: ignore[arg-type]
    node = _fragment(data, values)
    return node if type(node) is VNode else to_text_vnode(node)


def _fragment(parts: tuple[Any, ...], values: tuple[Any, ...]) -> Any:
    """Instantiate several top-level parts: one node (or string) stands alone, more make a fragment."""
    from .vnode import Fragment

    children: list[Any] = []
    for part in parts:
        if type(part) is str:
            children.append(part)
        elif type(part) is int:
            children.append(values[part])
        elif type(part) is _Compiled:
            children.append(VNode("_tpl", part, values))  # type: ignore[arg-type]
        else:
            children.append(_component(part, values))
    if len(children) == 1 and type(children[0]) in (VNode, str):
        return children[0]
    return Fragment(*children)


def _instantiate(program: _Program, values: tuple[Any, ...]) -> Any:
    kind, data = program
    if kind == "element":
        return VNode("_tpl", data, values)  # type: ignore[arg-type]
    return _fragment(data, values)


def _parts_value(parts: tuple[Any, ...], values: tuple[Any, ...]) -> Any:
    """The value of a partly interpolated attribute: a string, or a reactive getter."""
    reactive = False
    for part in parts:
        if type(part) is int and is_accessor(values[part]):
            reactive = True
            break

    def render() -> str:
        out: list[str] = []
        for part in parts:
            if type(part) is str:
                out.append(part)
            else:
                value = values[part]
                if is_accessor(value):
                    value = value()
                elif type(value) is Template:
                    value = render_template(value)
                out.append("" if value is None or value is False else str(value))
        return "".join(out)

    return render if reactive else render()


# Component-tag attribute names that are Python keywords.
_KEYWORD_PROPS = {"class": "class_", "for": "html_for"}

# How a component tag calls a callable that isn't an `@component`, per callable.
_CALL_KEYWORDS = 0  # f(children=[...], **props): flow controls, boundaries
_CALL_POSITIONAL = 1  # f(*children, **props): `Link`, context providers
_CALL_DICT = 2  # h(f, props): a plain function tag that takes the props dict
_call_styles: dict[Any, tuple[int, tuple[str, ...]]] = {}


def _call_style(comp: Any) -> tuple[int, tuple[str, ...]]:
    """How to call `comp`, and (positional style) the parameters before `*children`."""
    style = _call_styles.get(comp)
    if style is None:
        import inspect

        try:
            params = inspect.signature(comp).parameters.values()
        except TypeError, ValueError:
            params = []  # type: ignore[assignment]
        kinds = {p.kind for p in params}
        named = any(p.name == "children" and p.kind != inspect.Parameter.VAR_POSITIONAL for p in params)
        if named or inspect.Parameter.VAR_KEYWORD in kinds:
            style = (_CALL_KEYWORDS, ())
        elif inspect.Parameter.VAR_POSITIONAL in kinds:
            leading = []
            for p in params:
                if p.kind == inspect.Parameter.VAR_POSITIONAL:
                    break
                leading.append(p.name)
            style = (_CALL_POSITIONAL, tuple(leading))
        else:
            style = (_CALL_DICT, ())
        if len(_call_styles) < 1024:
            _call_styles[comp] = style
    return style


def _prop_name(name: str) -> str:
    return _KEYWORD_PROPS.get(name) or name.replace("-", "_")


def _component(node: _Component, values: tuple[Any, ...]) -> VNode:
    """Call a component tag's callable with its attributes and content.

    An `@component` gets keyword props (validated in dev mode). Other
    callables, such as the flow controls, boundaries, `Link`, and context
    providers, are called the way their signatures take children; a plain
    function that takes the props dictionary gets it as a node tag.
    """
    comp = values[node.index]
    if not callable(comp):
        raise TemplateError(f"A component tag needs a component, got {comp!r}")
    props: dict[str, Any] = {}
    for attr in node.attrs:
        kind = attr[0]
        if kind == _A_SPREAD:
            spread = values[attr[1]]
            if spread:
                props.update(spread)
        elif kind == _A_STATIC:
            props[_prop_name(attr[1])] = attr[2]
        elif kind == _A_VALUE:
            props[_prop_name(attr[1])] = values[attr[2]]
        else:
            props[_prop_name(attr[1])] = _parts_value(attr[2], values)
    content: list[Any] = []
    if node.children:
        child = _instantiate(node.children[0], values)
        # Several nodes of content are several children, as with item syntax.
        if type(child) is VNode and child.tag == "_fragment" and child.key is None:
            content = child.children
        else:
            content = [child]
    from .component import Component

    if isinstance(comp, Component):
        if content:
            props["children"] = content
        return comp(**props)
    style, leading = _call_style(comp)
    if style == _CALL_POSITIONAL:
        # Parameters before `*children` (a provider's `value`) go first.
        args = [props.pop(name) for name in leading if name in props]
        result = comp(*args, *content, **props)
    elif style == _CALL_KEYWORDS:
        if content:
            props["children"] = content[0] if len(content) == 1 else content
        result = comp(**props)
    else:
        from .vnode import h

        if content:
            props["children"] = content
        return h(comp, props)
    if not isinstance(result, VNode):
        raise TemplateError(f"Component tag {getattr(comp, '__name__', comp)!r} didn't return a node")
    return result


# ---------------------------------------------------------------------------
# Expansion (server rendering, hydration, SVG, and backends without templates)
# ---------------------------------------------------------------------------


def _expand_props(attrs: list[tuple[Any, ...]], values: tuple[Any, ...]) -> dict[str, Any]:
    props: dict[str, Any] = {}
    for attr in attrs:
        kind = attr[0]
        if kind == _A_SPREAD:
            spread = values[attr[1]]
            if spread:
                props.update(spread)
            continue
        name = attr[1]
        if kind == _A_STATIC:
            props[name] = attr[2]
            continue
        event = _event_prop(name)
        if event is not None:
            props[event] = values[attr[2]]
        elif kind == _A_PARTS:
            props[name] = _parts_value(attr[2], values)
        else:
            props[name] = values[attr[2]]
    return props


def _expand_node(node: Any, values: tuple[Any, ...]) -> Any:
    if isinstance(node, str):
        return node
    if isinstance(node, tuple):  # raw text
        return node[1]
    if isinstance(node, _Slot):
        return values[node.index]
    if isinstance(node, _Component):
        return _component(node, values)
    return VNode(
        node.tag,
        _expand_props(node.attrs, values),
        flatten_children([_expand_node(child, values) for child in node.children]),
    )


def expand(vnode: VNode) -> VNode:
    """Build the ordinary VNode tree a template instance stands for."""
    compiled: _Compiled = vnode.props  # type: ignore[assignment]
    tree: VNode = _expand_node(compiled.root, vnode.children)  # type: ignore[arg-type]
    return tree


# ---------------------------------------------------------------------------
# Mounting, patching, and disposal (clone path)
# ---------------------------------------------------------------------------

# Reconciler functions, bound on first use (the reconciler imports this module).
# A test reloading the reconciler re-executes it into the same module dict,
# so functions bound here keep working.
_mount_hole: Any = None
_region_set: Any = None
_dispose_tree: Any = None
_replace_hole_getter: Any = None


def _bind_reconciler() -> None:
    global _mount_hole, _region_set, _dispose_tree, _replace_hole_getter
    from . import reconciler

    _mount_hole = reconciler._mount_hole
    _region_set = reconciler._region_set
    _dispose_tree = reconciler._dispose_tree
    _replace_hole_getter = reconciler._replace_hole_getter


def _text_hole(nid: int, text: str) -> VNode:
    """Turn a child slot holding text in its placeholder into a hole region."""
    hole = VNode("_hole", {}, [])
    hole.el = nid
    hole._frag_end = nid
    hole._hole_text = text
    return hole


def mount(vnode: VNode, parent_id: int, anchor_id: int | None) -> None:
    """Mount a template instance with one clone command, then fill its slots.

    Each compiled template has a generated mount function (see
    `_generate`): straight-line code with its offsets and names as
    constants. A child slot whose value is text keeps it in its
    placeholder and records the string; any other child slot records the
    hole region it mounted.
    """
    if diagnostics._active is not None:
        diagnostics._active.counts["template_clones"] += 1
    vnode.props.mount(vnode, parent_id, anchor_id)  # type: ignore[attr-defined]


def _generate_and_mount(vnode: VNode, parent_id: int, anchor_id: int | None) -> None:
    compiled: _Compiled = vnode.props  # type: ignore[assignment]
    compiled.mount = _generate(compiled)
    compiled.mount(vnode, parent_id, anchor_id)


def _child_slot(value: Any, parent_id: int, nid: int, op: list[Any] | None, slot: int) -> Any:
    """Mount a child slot's value that isn't text in a text placeholder."""
    if _region_set is None:
        _bind_reconciler()
    hole = VNode("_hole", {}, [])
    if is_accessor(value):
        hole.props["getter"] = value
        if op is not None:
            _mount_hole(hole, parent_id, None, nid, None, True, op, slot)
        else:
            _mount_hole(hole, parent_id, None, nid, None, False)
        return hole
    hole.el = nid
    hole._frag_end = nid
    if op is not None:
        hole._hole_text = ""
    _region_set(hole, parent_id, nid, value)
    return hole


def _component_slot(node: _Component, values: tuple[Any, ...], parent_id: int, nid: int) -> VNode:
    if _region_set is None:
        _bind_reconciler()
    hole = VNode("_hole", {}, [])
    hole.el = nid
    hole._frag_end = nid
    _region_set(hole, parent_id, nid, _component(node, values))
    return hole


def _prop_slot(nid: int, name: str, value: Any) -> Any:
    getter = binding_value(name, value)
    if getter is not None:
        return _bind_reactive_prop(nid, name, getter, _FRESH, False)
    _apply_single_prop(nid, name, _FRESH, value)
    return None


def _parts_slot(nid: int, name: str, parts: tuple[Any, ...], values: tuple[Any, ...]) -> Any:
    value = _parts_value(parts, values)
    if callable(value):
        return _bind_reactive_prop(nid, name, value, _FRESH, False)
    if value:
        _apply_single_prop(nid, name, _FRESH, value)
    return None


def _spread_slot(nid: int, spread: Any) -> Any:
    if not spread:
        return spread
    spread = dict(spread)
    apply_initial_props(nid, spread)
    attach_ref(spread, nid)
    return spread


def _ref_slot(nid: int, ref: Any) -> None:
    if ref is not None:
        attach_ref({"ref": ref}, nid)


# Framework names a generated mount function closes over.
_CELLS = (
    "C",
    "PLAN",
    "register",
    "alloc",
    "emit",
    "OP_CLONE",
    "events",
    "bind_event",
    "prop_slot",
    "parts_slot",
    "spread_slot",
    "ref_slot",
    "child_slot",
    "component_slot",
)

# Set to a list to collect generated sources (tests and debugging).
_debug_sources: list[str] | None = None


def _generate(compiled: _Compiled) -> Callable[[VNode, int, int | None], None]:
    """Generate the straight-line mount function for one compiled template."""
    texts = len(compiled.texts)
    lines = [
        "def factory(" + ", ".join(_CELLS) + "):",
        "    def mount(vnode, parent, anchor):",
        "        values = vnode.children",
        "        first = alloc(" + str(compiled.count) + ")",
        "        op = [OP_CLONE, first, C.tpl or register(C), parent, anchor" + ', ""' * texts + "]",
        "        emit(op)",
        "        vnode.el = first",
        "        vnode.tpl = C",
    ]
    out: list[str] = []
    for k, slot in enumerate(compiled.plan):
        kind = slot[0]
        nid = f"first + {slot[1]}" if slot[1] else "first"
        d = f"d{k}"
        out.append(d)
        if kind == _S_PROP:
            lines.append(f"        {d} = prop_slot({nid}, {slot[3]!r}, values[{slot[2]}])")
        elif kind == _S_PARTS:
            lines.append(f"        {d} = parts_slot({nid}, {slot[3]!r}, PLAN[{k}][2], values)")
        elif kind == _S_EVENT:
            lines.append(f"        v = values[{slot[2]}]")
            if slot[5]:
                lines.append("        if type(v) is not events.EventHandler and callable(v):")
                lines.append(f"            events.bind_delegated({nid}, {slot[4]!r}, {slot[3]!r}, v)")
                lines.append("        else:")
                lines.append(f"            bind_event({nid}, PLAN[{k}], v)")
            else:
                lines.append(f"        bind_event({nid}, PLAN[{k}], v)")
            lines.append(f"        {d} = None")
        elif kind == _S_REF:
            lines.append(f"        ref_slot({nid}, values[{slot[2]}])")
            lines.append(f"        {d} = None")
        elif kind == _S_SPREAD:
            lines.append(f"        {d} = spread_slot({nid}, values[{slot[2]}])")
        elif kind == _S_CHILD:
            parent = f"first + {slot[3]}" if slot[3] else "first"
            text_slot = slot[4]
            lines.append(f"        v = values[{slot[2]}]")
            if text_slot >= 0:
                index = 5 + text_slot
                lines.append("        tv = type(v)")
                lines.append("        if tv is str:")
                lines.append(f"            op[{index}] = {d} = v")
                lines.append("        elif tv is int or tv is float:")
                lines.append(f"            op[{index}] = {d} = str(v)")
                lines.append("        else:")
                lines.append(f"            {d} = child_slot(v, {parent}, {nid}, op, {index})")
            else:
                lines.append(f"        {d} = child_slot(v, {parent}, {nid}, None, -1)")
        else:  # _S_COMPONENT
            parent = f"first + {slot[3]}" if slot[3] else "first"
            lines.append(f"        {d} = component_slot(PLAN[{k}][2], values, {parent}, {nid})")
    lines.append("        vnode.dyn = (" + "".join(f"{d}, " for d in out) + ")")
    lines.append("    return mount")
    source = "\n".join(lines)
    if _debug_sources is not None:
        _debug_sources.append(source)
    namespace: dict[str, Any] = {}
    exec(compile(source, f"<wybthon html {compiled.root.tag}>", "exec"), namespace)
    cells = {
        "C": compiled,
        "PLAN": compiled.plan,
        "register": kernel.register_template,
        "alloc": kernel.alloc_ids,
        "emit": kernel.emit,
        "OP_CLONE": kernel.OP_CLONE,
        "events": _events,
        "bind_event": _bind_event,
        "prop_slot": _prop_slot,
        "parts_slot": _parts_slot,
        "spread_slot": _spread_slot,
        "ref_slot": _ref_slot,
        "child_slot": _child_slot,
        "component_slot": _component_slot,
    }
    mount_fn: Callable[[VNode, int, int | None], None] = namespace["factory"](*(cells[name] for name in _CELLS))
    return mount_fn


def _bind_event(nid: int, slot: tuple[Any, ...], handler: Any) -> None:
    name = slot[3]
    if not callable(handler):
        if handler is not None:
            raise TypeError(f"{name} must be callable, got {handler!r}")
        if slot[5]:
            kernel.emit((kernel.OP_UNLISTEN, nid, slot[4]))
        return
    if slot[5]:
        if type(handler) is _events.EventHandler:
            # Native listener options need a direct listener: drop the
            # delegated mark the clone made, so the handler fires once.
            kernel.emit((kernel.OP_UNLISTEN, nid, slot[4]))
            _events.set_handler(nid, name, handler)
        else:
            _events.bind_delegated(nid, slot[4], name, handler)
    else:
        _events.set_handler(nid, name, handler)


def patch(old: VNode, new: VNode, parent_id: int) -> None:
    """Patch an instance with a new instance of the same compiled template, slot by slot."""
    if _region_set is None:
        _bind_reconciler()
    compiled: _Compiled = old.tpl
    first = old.el
    assert first is not None
    new.el = first
    new.tpl = compiled
    old_values: tuple[Any, ...] = old.children  # type: ignore[assignment]
    values: tuple[Any, ...] = new.children  # type: ignore[assignment]
    dyn = list(old.dyn or ())
    for k, slot in enumerate(compiled.plan):
        kind = slot[0]
        nid = first + slot[1]
        if kind == _S_COMPONENT:
            _region_set(dyn[k], first + slot[3], nid, _component(slot[2], values))
            continue
        if kind == _S_PARTS:
            parts = slot[2]
            if all(type(p) is str or values[p] is old_values[p] for p in parts):
                continue
            comp = dyn[k]
            if comp is not None:
                comp.dispose()
                dyn[k] = None
            value = _parts_value(parts, values)
            if callable(value):
                dyn[k] = _bind_reactive_prop(nid, slot[3], value, _FRESH, False)
            else:
                _apply_single_prop(nid, slot[3], _FRESH, value)
            continue
        index = slot[2]
        value = values[index]
        previous = old_values[index]
        if value is previous:
            continue
        if kind == _S_PROP:
            comp = dyn[k]
            if comp is not None:
                comp.dispose()
                dyn[k] = None
            getter = binding_value(slot[3], value)
            if getter is not None:
                dyn[k] = _bind_reactive_prop(nid, slot[3], getter, _FRESH, False)
            elif not (type(value) is type(previous) and value == previous):
                _apply_single_prop(nid, slot[3], _FRESH, value)
        elif kind == _S_EVENT:
            mapping = _events._handlers.get(nid)
            if mapping is not None:
                mapping.pop(slot[4], None)
            _bind_event(nid, slot, value)
        elif kind == _S_REF:
            detach_ref(nid)
            if value is not None:
                attach_ref({"ref": value}, nid)
        elif kind == _S_SPREAD:
            spread = dict(value) if value else {}
            apply_props(nid, dyn[k] or {}, spread)
            if spread.get("ref") is not (dyn[k] or {}).get("ref"):
                detach_ref(nid)
                attach_ref(spread, nid)
            dyn[k] = spread
        else:  # _S_CHILD
            hole = dyn[k]
            if type(hole) is str:
                vtype = type(value)
                if vtype is str or vtype is int or vtype is float:
                    text = value if vtype is str else str(value)
                    if text != hole:
                        kernel.emit((kernel.OP_SET_TEXT, nid, text))
                        dyn[k] = text
                    continue
                hole = dyn[k] = _text_hole(nid, hole)
            if is_accessor(value) or hole.render_effect is not None:
                dyn[k] = _replace_hole_getter(hole, first + slot[3], value)
            else:
                _region_set(hole, first + slot[3], nid, value)
    new.dyn = tuple(dyn)
    old.dyn = None
    old.tpl = None
    old.el = None


def dispose(vnode: VNode, owned: bool = False) -> None:
    """Tear down a cloned instance: handlers, refs, bindings, and dynamic children.

    The native nodes are released by the kernel when their range is
    disposed. With `owned`, the instance's owner is about to be disposed
    (a list row leaving), which disposes its binding computations.
    """
    if _dispose_tree is None:
        _bind_reconciler()
    compiled: _Compiled | None = vnode.tpl
    first = vnode.el
    if compiled is None or first is None:
        return
    handlers = _events._handlers
    for offset in compiled.handlers:
        mapping = handlers.pop(first + offset, None)
        if mapping:
            for handler in mapping.values():
                if handler.task_owner is not None:
                    handler.task_owner.dispose()
    for offset in compiled.refs:
        detach_ref(first + offset)
    for offset in compiled.spreads:
        nid = first + offset
        detach_ref(nid)
        remove_bindings_for(nid)
        mapping = handlers.pop(nid, None)
        if mapping:
            for handler in mapping.values():
                if handler.task_owner is not None:
                    handler.task_owner.dispose()
    dyn = vnode.dyn
    if dyn:
        for k, slot in enumerate(compiled.plan):
            item = dyn[k]
            if item is None or type(item) is str:
                continue
            kind = slot[0]
            if kind == _S_CHILD or kind == _S_COMPONENT:
                if owned:
                    # The owner disposes the hole's effect and scope; only
                    # its mounted content has per-node registrations.
                    sub_tree = item.subtree
                    if sub_tree is not None:
                        _dispose_tree(sub_tree)
                        item.subtree = None
                    item.el = None
                else:
                    _dispose_tree(item)
            elif (kind == _S_PROP or kind == _S_PARTS) and not owned:
                item.dispose()
    vnode.el = None
    vnode.tpl = None
    vnode.dyn = None


def is_template(vnode: Any) -> bool:
    """Whether `vnode` is a template instance (`html(t"...")` with one element root)."""
    return type(vnode) is VNode and vnode.tag == "_tpl"


def copy(vnode: VNode, copy_value: Callable[[Any], Any]) -> VNode:
    """A structural copy of an unmounted template instance (server rendering)."""
    values: tuple[Any, ...] = vnode.children  # type: ignore[assignment]
    return VNode("_tpl", vnode.props, tuple(copy_value(v) for v in values))  # type: ignore[arg-type]
