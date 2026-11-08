"""Server rendering straight to HTML strings (RFC 0006).

The browser mounts a tree by emitting DOM commands; a server render only
needs the HTML those commands would produce. This module walks the same
tree the reconciler mounts (components, holes, regions, templates) and
appends markup to a list of strings instead, so a server render builds no
DOM, sends no commands, and serializes nothing afterwards.

The output is exactly what `hydrate` expects: the comment markers a
region, hole, or fragment leaves in the browser's DOM, the hydration keys
of memos, boundaries, and ids (positions are assigned as the reconciler
assigns them), and the attributes a mounted element would serialize to.

Reactivity runs in its server form. Components run once, under the
owners they'd have in the browser, so context, error boundaries, and
`Loading` registration work unchanged. Each expression is evaluated
once and nothing subscribes: a server render never updates, so it needs
no computations for its bindings. `Loading` boundaries decide between
their content and their fallback once the whole tree has rendered (when
every boundary under a `Reveal` has registered), so a boundary is a
deferred part of the output rather than a string.
"""

from __future__ import annotations

from html import escape
from string.templatelib import Template
from typing import Any

from . import reconciler, templates
from ._dom_props import (
    _BOOLEAN_ATTRS,
    KIND_EVENT,
    KIND_REF,
    KIND_SKIP,
    _class_string,
    attr_name,
    binding_value,
    prop_kind,
    to_kebab,
)
from ._html_rules import LEADING_NEWLINE_ELEMENTS, RAW_TEXT_ELEMENTS, VOID_ELEMENTS
from ._warnings import component_name, log_error
from .component import Component
from .reactivity import _core
from .reactivity._core import NotReadyError, Owner, _ComponentContext, _Getter, _run_callback_body
from .vnode import VNode, is_accessor

__all__ = ["Boundary", "render", "join"]

# The marker a hole, region, or fragment leaves in the DOM.
_MARK = "<!---->"
# The marker after a claimed template slot's content (see `Renderer.claimed`).
_SLOT_MARK = "<!--$-->"
# A `NoHydration` region's marker (see `wybthon.flow`).
_NO_HYDRATION = "wyb:nh"

_NOT_READY = object()
_FAILED = object()

# Component bodies replaced by a server version, keyed by component.
_server_bodies: dict[Any, Any] = {}

# Bound on first use (they import modules that import this one).
_regions: Any = None


def _escape_text(text: str) -> str:
    if "&" in text or "<" in text or ">" in text:
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return text


def _escape_comment(text: str) -> str:
    return text.replace("--", "- -").replace(">", "&gt;")


def _open_marker(marker: str | None) -> str:
    return f"<!--{_escape_comment(marker)}-->" if marker else _MARK


def _close_marker(marker: str | None) -> str:
    return f"<!--{_escape_comment('/' + marker)}-->" if marker else _MARK


class Boundary:
    """A `Loading` boundary's place in the output, decided once the tree has rendered.

    Attributes:
        key: The boundary's hydration key (its comment markers' data).
        mode: `"content"`, `"fallback"`, or `"hidden"`, once resolved.
        parts: The output between the boundary's markers, once resolved.
    """

    __slots__ = ("key", "mode", "parts", "_resolve")

    def __init__(self, key: str | None, resolve: Any) -> None:
        self.key = key
        self.mode = "content"
        self.parts: list[Any] = []
        self._resolve = resolve

    def resolve(self) -> None:
        resolve, self._resolve = self._resolve, None
        if resolve is not None:
            resolve(self)

    def inner_html(self, reached: set[Boundary] | None = None) -> str:
        """The HTML between the boundary's markers."""
        return join(self.parts, reached)


def join(parts: list[Any], reached: set[Boundary] | None = None) -> str:
    """Join rendered parts into HTML, recording the boundaries the output contains in `reached`."""
    out: list[str] = []
    _join(parts, out, reached)
    return "".join(out)


def _join(parts: list[Any], out: list[str], reached: set[Boundary] | None) -> None:
    for part in parts:
        if type(part) is str:
            out.append(part)
        else:
            if reached is not None and type(part) is Boundary:
                reached.add(part)
            _join(part.parts, out, reached)


class _ErroredPart:
    """An `Errored` boundary's output: its content, or its fallback once it has caught an error."""

    __slots__ = ("parts", "error", "fn", "position", "pk", "ns", "select", "owner", "scope", "failed")

    def __init__(self, error: Any, fn: Any, position: str, pk: str | None, ns: str | None, select: Any, owner: Any):
        self.parts: list[Any] = []
        self.error = error
        self.fn = fn
        self.position = position
        self.pk = pk
        self.ns = ns
        self.select = select
        self.owner = owner
        self.scope: Owner | None = None
        self.failed = False


# Rounds of re-rendering `Errored` fallbacks (each can raise again or start
# boundaries) before a server render stops.
_MAX_SETTLE_ROUNDS = 8


class _TplElement:
    """A template element in a child list, rendered from its instance's values."""

    __slots__ = ("node", "values", "pk")

    def __init__(self, node: Any, values: tuple[Any, ...]) -> None:
        self.node = node
        self.values = values
        self.pk: str | None = None


class _Select:
    """A controlled `<select>`'s value, which decides its options' `selected` state."""

    __slots__ = ("prop", "value")

    def __init__(self, prop: str, value: Any) -> None:
        self.prop = prop
        self.value = value


def _dispatch(exc: BaseException, what: str) -> None:
    """Route an error to the nearest `Errored` boundary, or log it."""
    if not reconciler._dispatch_to_error_boundary(exc):
        log_error(f"{what} failed: {exc}", exc if isinstance(exc, Exception) else None)


def _evaluate(fn: Any, position: str | None) -> Any:
    """Evaluate an expression once, untracked: its value, `_NOT_READY`, or `_FAILED`."""
    previous = _core._enter_position(position) if position is not None else ""
    prev_obs = _core._current_observer
    _core._current_observer = None
    try:
        return fn()
    except NotReadyError:
        return _NOT_READY
    except Exception as exc:
        _dispatch(exc, "Reactive expression")
        return _FAILED
    finally:
        _core._current_observer = prev_obs
        if position is not None:
            _core._restore_position(previous)


def _attributes(tag: str, props: dict[str, Any], select: _Select | None) -> tuple[str, Any, Any, _Select | None]:
    """An element's serialized attributes, its text content override, and its select state.

    Mirrors what the prop writers in `wybthon._dom_props` would set on a
    freshly created element, and how a mounted element serializes.
    Returns `(attributes, textarea value, inner HTML, select state)`.
    """
    attrs: dict[str, str] = {}
    style: dict[str, str] | None = None
    value: str | None = None
    checked = False
    inner: str | None = None
    controlled: _Select | None = None
    for name, raw in props.items():
        kind = prop_kind(name)
        if kind == KIND_SKIP or kind == KIND_REF or kind == KIND_EVENT:
            continue
        getter = binding_value(name, raw)
        if getter is not None:
            v = _evaluate(getter.fn if type(getter) is _Getter else getter, None)
            if v is _NOT_READY or v is _FAILED:
                continue
        else:
            v = raw
        if name == "class" or name == "class_":
            text = v if type(v) is str else _class_string(v)
            if text:
                attrs["class"] = text
        elif name == "style":
            if isinstance(v, str):
                attrs["style"] = v
                style = {}
                for decl in v.split(";"):
                    if ":" in decl:
                        key, decl_value = decl.split(":", 1)
                        if key.strip():
                            style[key.strip()] = decl_value.strip()
            elif isinstance(v, dict):
                if style is None:
                    style = {}
                for key, decl_value in v.items():
                    if decl_value is not None and decl_value is not False:
                        style[to_kebab(key)] = str(decl_value)
        elif name == "dataset":
            if isinstance(v, dict):
                for key, data_value in v.items():
                    if data_value is not None and data_value is not False:
                        attrs[f"data-{to_kebab(str(key))}"] = "" if data_value is True else str(data_value)
        elif name == "value":
            if v is not None:
                value = str(v)
                if tag == "select":
                    controlled = _Select("value", value)
        elif name == "selected_values":
            if tag == "select":
                controlled = _Select("selectedValues", [str(item) for item in (v or [])])
        elif name == "checked":
            if v:
                checked = True
        elif name == "inner_html" or name == "innerHTML":
            if v is not None:
                inner = str(v)
        elif v is not None and v is not False:
            attr = attr_name(name)
            if v is True:
                attrs[attr] = "" if attr in _BOOLEAN_ATTRS else "true"
            else:
                attrs[attr] = v if type(v) is str else str(v)
    if style:
        attrs["style"] = "; ".join(f"{key}: {decl}" for key, decl in style.items())
    else:
        attrs.pop("style", None)
    # An option's value as the browser's controlled-select pass reads it: the
    # property when it's set and non-empty, otherwise the attribute.
    option_value = (value or attrs.get("value")) if tag == "option" else None
    textarea: str | None = None
    if value is not None:
        if tag == "textarea":
            textarea = value
        elif tag != "select":
            attrs["value"] = value
    if checked:
        attrs["checked"] = ""
    if tag == "option" and select is not None:
        if select.prop == "selectedValues":
            on = option_value in (select.value or [])
        else:
            on = option_value == select.value
        if on:
            attrs["selected"] = ""
        else:
            attrs.pop("selected", None)
    parts = [f" {name}" if text == "" else f' {name}="{escape(text, quote=True)}"' for name, text in attrs.items()]
    return "".join(parts), textarea, inner, controlled


class _Renderer:
    """One server render: walks the tree and appends HTML parts."""

    __slots__ = ("boundaries", "errored", "static")

    def __init__(self) -> None:
        # Depth of `NoHydration` regions: the browser never claims what's
        # inside, so templates there are written without slot placeholders.
        self.static = 0
        # Boundaries waiting to be resolved, in creation order.
        self.boundaries: list[Boundary] = []
        # Every `Errored` boundary rendered, in case one catches an error late.
        self.errored: list[_ErroredPart] = []

    # -- dispatch -------------------------------------------------------------

    def node(
        self, v: Any, out: list[Any], ns: str | None, raw: bool, select: _Select | None, anchored: bool = False
    ) -> None:
        """Render one normalized child: a VNode or a template element.

        `anchored`: `v` is a hole's whole content, so a list, branch, or
        fragment writes no markers of its own (the hole's marker ends it),
        as the client mounts it.
        """
        if type(v) is _TplElement:
            self.template_element(v.node, v.values, out, v.pk, ns, select)
            return
        owner = v.owner_scope
        if owner is not None:
            prev_owner = _core._current_owner
            prev_obs = _core._current_observer
            _core._current_owner = owner
            _core._current_observer = None
            try:
                self.dispatch(v, out, ns, raw, select, anchored)
            finally:
                _core._current_owner = prev_owner
                _core._current_observer = prev_obs
            return
        self.dispatch(v, out, ns, raw, select, anchored)

    def dispatch(
        self, v: VNode, out: list[Any], ns: str | None, raw: bool, select: _Select | None, anchored: bool = False
    ) -> None:
        tag = v.tag
        if tag == "_text":
            text = v.props.get("nodeValue", "")
            out.append(text if raw else _escape_text(text))
        elif tag == "_tpl":
            compiled: Any = v.props
            values: Any = v.children
            if ns is None and compiled.claimable and not self.static:
                self.claimed(compiled, values, out, getattr(v, "pk", None) or _core._position)
            else:
                self.template_element(compiled.root, values, out, getattr(v, "pk", None), ns, select)
        elif tag == "_hole":
            self.hole(v.props.get("getter"), out, getattr(v, "pk", None), ns, raw, select)
        elif tag == "_list":
            self.list_region(v, out, ns, select, anchored)
        elif tag == "_branch":
            self.branch_region(v, out, ns, select, anchored)
        elif tag == "_fragment":
            marker = v.props.get("marker")
            if anchored and not marker and v.key is None:
                self.children(v.children, getattr(v, "pk", None), out, ns, raw, select)
                return
            out.append(_open_marker(marker))
            static = marker == _NO_HYDRATION
            self.static += static
            try:
                self.children(v.children, getattr(v, "pk", None), out, ns, raw, select)
            finally:
                self.static -= static
            out.append(_close_marker(marker))
        elif tag == "_ssr_boundary":
            self.loading(v, out, ns, select)
        elif tag == "_static":
            marker = v.props.get("marker")
            out.append(_open_marker(marker))
            out.append(_close_marker(marker))
        elif callable(tag):
            self.component(v, out, ns, select)
        else:
            self.element(tag, v.props, v.children, out, getattr(v, "pk", None), ns, select)

    def children(
        self, items: list[Any], pk: str | None, out: list[Any], ns: str | None, raw: bool, select: _Select | None
    ) -> None:
        if items:
            self.emit(items, pk or _core._position, 0, out, ns, raw, select)

    def emit(
        self, items: Any, base: str, i: int, out: list[Any], ns: str | None, raw: bool, select: _Select | None
    ) -> int:
        """Render children as `flatten_children` and `normalize_children` would list them.

        `i` is the position of the next child under `base`; returns the
        position after the last one rendered.
        """
        for ch in items:
            t = type(ch)
            if t is str:
                out.append(ch if raw else _escape_text(ch))
                i += 1
            elif t is _TplElement:
                self.template_element(ch.node, ch.values, out, f"{base}.{i}", ns, select)
                i += 1
            elif t is VNode or isinstance(ch, VNode):
                if ch.tag == "_fragment" and ch.owner_scope is None and ch.key is None:
                    i = self.emit(ch.children, base, i, out, ns, raw, select)
                else:
                    ch.pk = f"{base}.{i}"
                    i += 1
                    self.node(ch, out, ns, raw, select)
            elif ch is None or ch is True or ch is False:
                continue
            elif t is list or t is tuple:
                i = self.emit(ch, base, i, out, ns, raw, select)
            elif t is Template:
                raise TypeError('A t-string is only markup when it\'s passed to html(): html(t"...")')
            elif is_accessor(ch):
                self.hole(ch, out, f"{base}.{i}", ns, raw, select)
                i += 1
            elif isinstance(ch, (list, tuple)):
                i = self.emit(ch, base, i, out, ns, raw, select)
            else:
                text = str(ch)
                out.append(text if raw else _escape_text(text))
                i += 1
        return i

    # -- elements -------------------------------------------------------------

    def element(
        self,
        tag: str,
        props: dict[str, Any],
        children: list[Any],
        out: list[Any],
        pk: str | None,
        ns: str | None,
        select: _Select | None,
    ) -> None:
        el_ns = reconciler._element_ns(tag, ns)
        lower = tag.lower()
        attrs, textarea, inner, controlled = _attributes(lower, props, select)
        out.append(f"<{tag}{attrs}>")
        if lower in VOID_ELEMENTS and el_ns is None:
            return
        child_ns = reconciler._child_ns(tag, ns)
        inner_select = controlled if lower == "select" else select
        if textarea is not None or inner is not None:
            # The content comes from a property; the children still mount.
            self.children(children, pk, [], child_ns, False, inner_select)
            if inner is not None:
                out.append(inner)
            else:
                assert textarea is not None
                out.append(("\n" if textarea.startswith("\n") else "") + _escape_text(textarea))
        else:
            start = len(out)
            self.children(children, pk, out, child_ns, lower in RAW_TEXT_ELEMENTS, inner_select)
            if lower in LEADING_NEWLINE_ELEMENTS and len(out) > start:
                first = out[start]
                if type(first) is str and first.startswith("\n"):
                    out.insert(start, "\n")
        out.append(f"</{tag}>")

    def template_element(
        self, node: Any, values: tuple[Any, ...], out: list[Any], pk: str | None, ns: str | None, select: _Select | None
    ) -> None:
        """Render a template's element with its instance's values (no VNode tree is built)."""
        plan = _plans.get(node)
        if plan is None:
            plan = _plans[node] = _plan(node)
        if ns is not None or select is not None or plan[0] == _DYNAMIC:
            props = templates._expand_props(node.attrs, values)
            if ns is not None or select is not None or plan[2]:
                # Content the element itself may decide (raw text, a `value`,
                # inner HTML, a spread that could carry either) or a
                # namespace: the general element path.
                items: list[Any] = []
                for child in node.children:
                    t = type(child)
                    if t is str:
                        items.append(child)
                    elif t is templates._Slot:
                        items.append(values[child.index])
                    elif t is templates._Element:
                        items.append(_TplElement(child, values))
                    elif t is tuple:
                        items.append(child[1])
                    else:
                        items.append(templates._component(child, values))
                self.element(node.tag, props, items, out, pk, ns, select)
                return
            attrs = _attributes(node.tag.lower(), props, None)[0]
            out.append(f"<{node.tag}{attrs}>")
            if plan[1]:
                return
            self.template_children(node, values, pk, out)
            out.append(f"</{node.tag}>")
            return
        if plan[0] == _STATIC_SUBTREE:
            out.append(plan[1])
            return
        out.append(plan[1])
        if plan[2] is not None:
            self.template_children(node, values, pk, out)
            out.append(plan[2])

    # -- claimed templates ----------------------------------------------------

    def claimed(self, compiled: Any, values: tuple[Any, ...], out: list[Any], pk: str) -> None:
        """Render a template instance in the layout its clone has, so hydration claims it in one command.

        Each child or component slot's content goes in front of a `$`
        comment, where the clone has the slot's placeholder; a text slot
        showing text is that text alone. The content of slot `k` is
        positioned at `<pk>.<k>`, as `wybthon.templates.claim` positions it.
        """
        slots = compiled.slot_of
        if slots is None:
            slots = compiled.slot_of = {}
            for k, slot in enumerate(compiled.plan):
                if slot[0] == templates._S_CHILD:
                    slots[("c", slot[2])] = k
                elif slot[0] == templates._S_COMPONENT:
                    slots[("t", id(slot[2]))] = k
        self.claimed_element(compiled.root, compiled, values, out, pk)

    def claimed_element(self, node: Any, compiled: Any, values: tuple[Any, ...], out: list[Any], pk: str) -> None:
        plan = _plans.get(node)
        if plan is None:
            plan = _plans[node] = _plan(node)
        if plan[0] == _STATIC_SUBTREE:
            out.append(plan[1])
            return
        if plan[0] == _STATIC_OPEN:
            out.append(plan[1])
            if plan[2] is not None:
                self.claimed_children(node, compiled, values, out, pk)
                out.append(plan[2])
            return
        attrs = _attributes(node.tag.lower(), templates._expand_props(node.attrs, values), None)[0]
        out.append(f"<{node.tag}{attrs}>")
        if plan[1]:
            return
        self.claimed_children(node, compiled, values, out, pk)
        out.append(f"</{node.tag}>")

    def claimed_children(self, node: Any, compiled: Any, values: tuple[Any, ...], out: list[Any], pk: str) -> None:
        slots = compiled.slot_of
        for child in node.children:
            t = type(child)
            if t is str:
                out.append(_escape_text(child))
            elif t is templates._Element:
                self.claimed_element(child, compiled, values, out, pk)
            elif t is templates._Slot:
                k = slots[("c", child.index)]
                self.claimed_slot(values[child.index], compiled.plan[k][4] >= 0, out, f"{pk}.{k}")
            elif t is tuple:
                out.append(_escape_text(child[1]))
            else:
                k = slots[("t", id(child))]
                position = f"{pk}.{k}"
                previous = _core._enter_position(position)
                try:
                    node_ = templates._component(child, values)
                finally:
                    _core._restore_position(previous)
                self.content(node_, out, position, None, None)
                out.append(_SLOT_MARK)

    def claimed_slot(self, value: Any, text_slot: bool, out: list[Any], position: str) -> None:
        """A child slot's content and placeholder, as `wybthon.templates._child_slot` mounts it."""
        if type(value) is list and len(value) == 1:
            value = value[0]
        vt = type(value)
        if vt is str or vt is int or vt is float:
            out.append(_escape_text(value if vt is str else str(value)))
            if not text_slot:
                out.append(_SLOT_MARK)
            return
        if value is None or value is True or value is False:
            if not text_slot:
                out.append(_SLOT_MARK)
            return
        if is_accessor(value):
            fn = value.fn if vt is _Getter else value
            # A text slot's expression is a text binding; any other slot's is a hole's.
            result = _evaluate(fn, position if text_slot else position + "h")
            if result is _NOT_READY or result is _FAILED:
                if not text_slot:
                    out.append(_SLOT_MARK)
                return
            rt = type(result)
            if rt is str or rt is int or rt is float:
                out.append(_escape_text(result if rt is str else str(result)))
                if not text_slot:
                    out.append(_SLOT_MARK)
                return
            if result is None or result is True or result is False:
                if not text_slot:
                    out.append(_SLOT_MARK)
                return
            value = result
        self.content(value, out, position, None, None)
        out.append(_SLOT_MARK)

    def template_children(self, node: Any, values: tuple[Any, ...], pk: str | None, out: list[Any]) -> None:
        """A template element's children, in an HTML element with no namespace or select."""
        base = pk or _core._position
        i = 0
        for child in node.children:
            t = type(child)
            if t is str:
                out.append(_escape_text(child))
                i += 1
            elif t is templates._Element:
                self.template_element(child, values, out, f"{base}.{i}", None, None)
                i += 1
            elif t is templates._Slot:
                value = values[child.index]
                vt = type(value)
                if vt is _Getter:
                    self.hole(value, out, f"{base}.{i}", None, False, None)
                    i += 1
                elif vt is str:
                    out.append(_escape_text(value))
                    i += 1
                else:
                    i = self.emit((value,), base, i, out, None, False, None)
            elif t is tuple:
                out.append(_escape_text(child[1]))
                i += 1
            else:
                i = self.emit((templates._component(child, values),), base, i, out, None, False, None)

    # -- holes ----------------------------------------------------------------

    def hole(self, getter: Any, out: list[Any], pk: str | None, ns: str | None, raw: bool, select: Any) -> None:
        fn = getter.fn if type(getter) is _Getter else getter
        if not callable(fn):
            out.append(_MARK)
            return
        position = f"{pk or _core._position}h"
        result = _evaluate(fn, position)
        if result is _NOT_READY or result is _FAILED:
            out.append(_MARK)
            return
        rtype = type(result)
        if rtype is str or rtype is int or rtype is float:
            text = result if rtype is str else str(result)
            out.append(text if raw else _escape_text(text))
            return
        error = getattr(fn, "_wyb_error", None)
        if error is None:
            self.content(result, out, pk, ns, select)
            out.append(_MARK)
            return
        # An `Errored` boundary: its output is a part of its own, so an error
        # it catches after its content rendered can still replace it.
        part = _ErroredPart(error, fn, position, pk, ns, select, _core._current_owner)
        out.append(part)
        out.append(_MARK)
        part.scope = self.content(result, part.parts, pk, ns, select)
        self.errored.append(part)
        self.heal(part)

    def heal(self, part: _ErroredPart) -> bool:
        """Re-render an `Errored` boundary with its fallback if it caught an error; True when it did.

        The browser's boundary re-renders when its error signal changes, at
        the next flush; a server render does it here, once its content (or
        a later flush, or a boundary resolved afterwards) has raised.
        """
        error = part.error
        if part.failed:
            return False
        if error._staged:
            if error._pending is None:
                return False
            error._commit_revealed(error._pending)
        elif error._value is None:
            return False
        part.failed = True
        if part.scope is not None:
            part.scope.dispose()
        part.parts = []
        prev_owner = _core._current_owner
        _core._current_owner = part.owner
        try:
            result = _evaluate(part.fn, part.position)
            if result is not _NOT_READY and result is not _FAILED:
                part.scope = self.content(result, part.parts, part.pk, part.ns, part.select)
        finally:
            _core._current_owner = prev_owner
        return True

    def content(self, result: Any, out: list[Any], pk: str | None, ns: str | None, select: Any) -> Owner:
        """Render what a hole's expression returned under the hole's scope."""
        node = reconciler._coerce_result(result)
        node.pk = f"{pk or _core._position}.h"
        scope = Owner()
        parent = _core._current_owner
        if parent is not None:
            parent._add_child(scope)
        prev_owner = _core._current_owner
        prev_obs = _core._current_observer
        _core._current_owner = scope
        _core._current_observer = None
        try:
            self.node(node, out, ns, False, select, True)
        except Exception as exc:
            _dispatch(exc, "Reactive hole update")
        finally:
            _core._current_owner = prev_owner
            _core._current_observer = prev_obs
        return scope

    # -- regions --------------------------------------------------------------

    def _scope(self, v: VNode) -> Owner:
        scope = v.scope = Owner()
        parent = _core._current_owner
        if parent is not None:
            parent._add_child(scope)
        return scope

    def list_region(self, v: VNode, out: list[Any], ns: str | None, select: Any, anchored: bool = False) -> None:
        global _regions
        if _regions is None:
            from . import _regions as regions

            _regions = regions
        if not anchored:
            out.append(_MARK)
        scope = self._scope(v)
        region = _regions._ListRegion(v, 0)
        value = _evaluate(region.prepare, None)
        if value is not _NOT_READY and value is not _FAILED:
            data = value.data
            if isinstance(value.source, _regions.StoreList):
                data = [_regions._wrap(item) for item in data]
            rows = []
            try:
                for index, item in enumerate(data):
                    rows.append(region.new_row(item, index, region.key(item)))
            except Exception as exc:
                _dispatch(exc, "List row")
            if rows:
                for row in rows:
                    self.node(row.vnode, out, ns, False, select)
            else:
                fallback = v.props.get("fallback")
                if fallback is not None:
                    owner = Owner()
                    scope._add_child(owner)
                    try:
                        node = reconciler._coerce_result(
                            _core._run_owned_untracked(owner, _regions._render_slot, fallback)
                        )
                        node.owner_scope = owner
                        self.node(node, out, ns, False, select)
                    except Exception as exc:
                        _dispatch(exc, "List fallback")
        if not anchored:
            out.append(_MARK)

    def branch_region(self, v: VNode, out: list[Any], ns: str | None, select: Any, anchored: bool = False) -> None:
        global _regions
        if _regions is None:
            from . import _regions as regions

            _regions = regions
        if not anchored:
            out.append(_MARK)
        scope = self._scope(v)
        region = _regions._BranchRegion(v, 0)
        selection = _evaluate(region.choose, None)
        if selection is not _NOT_READY and selection is not _FAILED:
            token, slot, args = selection
            if slot is not None:
                owner = Owner()
                scope._add_child(owner)
                position = f"{getattr(v, 'pk', None) or _core._position}.{token[0]}"
                previous = _core._enter_position(position)
                try:
                    try:
                        node = reconciler._coerce_result(
                            _run_callback_body(owner, _regions._BRANCH_SCOPE, _regions._render_slot, slot, *args)
                        )
                    finally:
                        _core._restore_position(previous)
                    node.pk = position
                    node.owner_scope = owner
                    self.node(node, out, ns, False, select)
                except Exception as exc:
                    _dispatch(exc, "Branch")
        if not anchored:
            out.append(_MARK)

    # -- components -----------------------------------------------------------

    def component(self, v: VNode, out: list[Any], ns: str | None, select: Any) -> None:
        comp: Any = v.tag
        ctx = _ComponentContext(comp)
        parent_owner = _core._current_owner
        if parent_owner is not None:
            parent_owner._add_child(ctx)
        position = f"{getattr(v, 'pk', None) or _core._position}:{component_name(comp)}"
        previous_position = _core._enter_position(position)
        saved = _core._enter_component_setup(ctx)
        try:
            try:
                body = _server_bodies.get(comp)
                if body is not None:
                    cls = comp._resolve()
                    result = body(cls._wyb_bind(v.props, False) if cls is not None else None)
                elif isinstance(comp, Component):
                    result, ctx._props = comp._render(v.props, False)
                else:
                    result = comp(v.props)
            except Exception as exc:
                if reconciler._dispatch_to_error_boundary(exc):
                    result = None
                else:
                    log_error(f"Render failed in component {component_name(comp)}", exc)
                    raise
        finally:
            _core._exit_component_setup(saved)
            _core._restore_position(previous_position)
        sub_tree = reconciler._coerce_result(result)
        sub_tree.pk = position + "/"
        prev_owner = _core._current_owner
        prev_obs = _core._current_observer
        _core._current_owner = ctx
        _core._current_observer = None
        mark = len(out)
        try:
            try:
                self.node(sub_tree, out, ns, False, select)
            except Exception as exc:
                if not reconciler._dispatch_to_error_boundary(exc):
                    raise
                del out[mark:]
        finally:
            _core._current_owner = prev_owner
            _core._current_observer = prev_obs

    # -- boundaries -----------------------------------------------------------

    def loading(self, v: VNode, out: list[Any], ns: str | None, select: Any) -> None:
        """A `Loading` boundary: markers around its content hole and its fallback hole.

        The content renders now, so async reads under it register with the
        boundary. Whether the output keeps it or shows the fallback is decided
        once the whole tree has rendered (see `resolve`).
        """
        props = v.props
        key = props["key"]
        marker = f"wyb:b{key}" if key is not None else None
        base = getattr(v, "pk", None) or _core._position
        out.append(_open_marker(marker))
        content: list[Any] = []
        self.hole(props["content"], content, f"{base}.0", ns, False, select)
        owner = _core._current_owner
        mode_of = props["mode"]
        fallback_for = props["fallback"]

        def resolve(boundary: Boundary) -> None:
            mode = boundary.mode = mode_of()
            parts = boundary.parts
            if mode == "content":
                parts.extend(content)
            prev_owner = _core._current_owner
            _core._current_owner = owner
            try:
                self.hole(fallback_for(mode), parts, f"{base}.1", ns, False, select)
            finally:
                _core._current_owner = prev_owner

        boundary = Boundary(key, resolve)
        out.append(boundary)
        self.boundaries.append(boundary)
        session = _core._session
        if key is not None and session is not None and session.mode == "server":
            session.boundaries.append((key, boundary))
        out.append(_close_marker(marker))

    def resolve(self) -> None:
        """Resolve every boundary, in creation order (resolving may create more)."""
        i = 0
        while i < len(self.boundaries):
            self.boundaries[i].resolve()
            i += 1

    def settle(self) -> None:
        """Flush, resolve boundaries, and re-render `Errored` boundaries that failed late, until stable."""
        for _ in range(_MAX_SETTLE_ROUNDS):
            _core.flush()
            self.resolve()
            _core.flush()
            healed = False
            for part in list(self.errored):
                healed |= self.heal(part)
            if not healed:
                return


# Template element plans, by parsed element (see `_plan`).
_DYNAMIC = 0
_STATIC_SUBTREE = 1
_STATIC_OPEN = 2
_plans: dict[Any, tuple[Any, ...]] = {}

# Elements whose content isn't only their children (raw text, a leading
# newline, a property), rendered by the general element path.
_VERBATIM = RAW_TEXT_ELEMENTS | LEADING_NEWLINE_ELEMENTS | {"select", "option"}


# Props that replace an element's children with their own content.
_CONTENT_PROPS = frozenset({"inner_html", "innerHTML"})


def _static_attrs(node: Any) -> bool:
    """Whether a template element's attributes render the same for every instance."""
    for attr in node.attrs:
        kind = attr[0]
        if kind == templates._A_STATIC:
            if attr[1] in ("value", "inner_html", "innerHTML", "checked"):
                return False
        elif kind == templates._A_VALUE:
            if templates._event_prop(attr[1]) is None and attr[1] != "ref":
                return False
        else:
            return False
    return True


def _static_props(node: Any) -> dict[str, Any]:
    """The props of a template element whose attributes are static (handlers and refs render nothing)."""
    return {attr[1]: attr[2] for attr in node.attrs if attr[0] == templates._A_STATIC}


def _static_subtree(node: Any) -> bool:
    if not _static_attrs(node) or node.tag.lower() in _VERBATIM:
        return False
    for child in node.children:
        t = type(child)
        if t is templates._Element:
            if not _static_subtree(child):
                return False
        elif t is not str:
            return False
    return True


def _plan(node: Any) -> tuple[Any, ...]:
    """How to render a template element: its whole HTML, its tags around its children, or neither.

    A dynamic plan's second item says whether the element is void, and its
    third whether it needs the general element path (its content may come
    from a prop, or it has a namespace).
    Static parts are rendered once, through the general element path, so
    they serialize exactly as it would.
    """
    tag = node.tag
    lower = tag.lower()
    void = lower in VOID_ELEMENTS
    general = (
        lower in _VERBATIM
        or reconciler._element_ns(tag, None) is not None
        or any(attr[0] == templates._A_SPREAD or attr[1] in _CONTENT_PROPS for attr in node.attrs)
    )
    if general:
        return (_DYNAMIC, void, True)
    if _static_subtree(node):
        renderer = _Renderer()
        out: list[Any] = []
        renderer.element(
            tag,
            _static_props(node),
            [_TplElement(c, ()) if type(c) is not str else c for c in node.children],
            out,
            "s",
            None,
            None,
        )
        return (_STATIC_SUBTREE, "".join(out))
    if _static_attrs(node):
        attrs, _textarea, _inner, _controlled = _attributes(lower, _static_props(node), None)
        return (_STATIC_OPEN, f"<{tag}{attrs}>", None if void else f"</{tag}>")
    return (_DYNAMIC, void, False)


# The renderer of the server render in progress.
_active: _Renderer | None = None


def render(node: VNode) -> list[Any]:
    """Render `node` (positioned at the root) into HTML parts; boundaries are resolved."""
    global _active
    if not _server_bodies:
        from .loading import _Loading, _server_loading

        _server_bodies[_Loading] = _server_loading
    renderer = _Renderer()
    previous = _active
    _active = renderer
    patchable = reconciler._patchable
    reconciler._patchable = False
    try:
        out: list[Any] = []
        node.pk = "r"
        renderer.node(node, out, None, False, None)
        renderer.settle()
        return out
    finally:
        reconciler._patchable = patchable
        _active = previous
