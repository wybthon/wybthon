"""DOM property application and diffing for element VNodes.

Translates VNode props into batched DOM ops (see `wybthon.kernel`),
including:

- **Controlled form elements** (`value`, `checked`) via DOM properties.
- **CSS style objects** (`{"backgroundColor": "red"}` → kebab-cased
  inline styles).
- **Dataset attributes** (`{"dataset": {"id": 5}}` → `data-id="5"`).
- **Event delegation** for `on_click` / `onClick` style handlers.
- **Reactive prop bindings**: callable prop values are wrapped in their
  own effect so updates re-apply only the affected prop, never the
  surrounding component.

Nothing here touches the DOM directly; every applier emits ops against
an integer node id, and the kernel applies the whole batch in one
bridge crossing at commit time.

This module is consumed by the reconciler; most application code never
imports from it directly.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

from . import kernel
from ._warnings import log_error
from .events import set_handler
from .kernel import OP_SET_ATTR, OP_SET_PROP, OP_SET_STYLE
from .vnode import is_getter

__all__: list = []

PropsDict = Dict[str, Any]

CAMEL_TO_KEBAB = re.compile(r"(?<!^)(?=[A-Z])")

# Sentinel used by reactive prop bindings to detect "first run".
_UNSET = object()


def to_kebab(name: str) -> str:
    """Convert a camelCase property name to kebab-case.

    Args:
        name: A camelCase string such as `"backgroundColor"`.

    Returns:
        The kebab-cased equivalent (e.g., `"background-color"`).
    """
    return CAMEL_TO_KEBAB.sub("-", name).lower()


def is_event_prop(name: str) -> bool:
    """Return True if `name` looks like an event handler prop.

    Both `on_click` (snake-case) and `onClick` (camelCase) styles are
    recognised.

    Args:
        name: Prop name to inspect.

    Returns:
        `True` for event handler props.
    """
    if name.startswith("on_"):
        return True
    return len(name) > 2 and name.startswith("on") and name[2].isupper()


def event_name_from_prop(name: str) -> str:
    """Convert an `on_click` / `onClick` prop name to its DOM event name.

    Args:
        name: Event handler prop name.

    Returns:
        The DOM event name (e.g., `"click"`, `"mouseover"`).
    """
    if name.startswith("on_"):
        return name[3:]
    if name.startswith("on"):
        return name[2:].lower()
    return name


def attach_ref(props: PropsDict, node_id: int) -> None:
    """Point `props["ref"].current` at an id-backed `Element` when present."""
    ref = props.get("ref")
    if ref is not None and hasattr(ref, "current"):
        from .dom import Element

        ref.current = Element(node_id=node_id)


def detach_ref(props: PropsDict) -> None:
    """Clear `props["ref"].current` when a `ref` prop is present."""
    ref = props.get("ref")
    if ref is not None and hasattr(ref, "current"):
        ref.current = None


# ---------------------------------------------------------------------------
# Per-prop appliers (used by both initial mount and per-prop reactive bindings)
# ---------------------------------------------------------------------------


def _apply_single_prop(node_id: int, name: str, old_val: Any, new_val: Any) -> None:
    """Emit ops applying (or diffing) a single prop on a DOM node.

    `old_val` may be the sentinel `_UNSET` for an initial application; in
    that case the prop is written unconditionally with no diff against
    a previous value.
    """
    if name in ("key", "ref"):
        return

    if is_event_prop(name):
        if old_val is not _UNSET and old_val is new_val:
            return
        set_handler(node_id, name, new_val if callable(new_val) else None)
        return

    if name in ("class", "className"):
        kernel.emit((OP_SET_ATTR, node_id, "class", _class_string(new_val)))
        return

    if name == "style":
        _apply_style(node_id, None if old_val is _UNSET else old_val, new_val)
        return

    if name == "dataset":
        _apply_dataset(node_id, None if old_val is _UNSET else old_val, new_val)
        return

    if name == "value":
        kernel.emit((OP_SET_PROP, node_id, "value", "" if new_val is None else str(new_val)))
        return

    if name == "checked":
        kernel.emit((OP_SET_PROP, node_id, "checked", bool(new_val)))
        return

    kernel.emit((OP_SET_ATTR, node_id, name, None if new_val is None else str(new_val)))


def _remove_single_prop(node_id: int, name: str, old_val: Any) -> None:
    """Emit ops removing a single prop from a DOM node."""
    if name in ("key", "ref"):
        return
    if is_event_prop(name):
        set_handler(node_id, name, None)
    elif name in ("class", "className"):
        kernel.emit((OP_SET_ATTR, node_id, "class", ""))
    elif name == "style":
        _remove_styles(node_id, old_val)
    elif name == "dataset":
        _remove_dataset(node_id, old_val)
    elif name == "value":
        kernel.emit((OP_SET_PROP, node_id, "value", ""))
    elif name == "checked":
        kernel.emit((OP_SET_PROP, node_id, "checked", False))
    else:
        kernel.emit((OP_SET_ATTR, node_id, name, None))


# ---------------------------------------------------------------------------
# Bulk appliers
# ---------------------------------------------------------------------------


def apply_props(node_id: int, old_props: PropsDict, new_props: PropsDict) -> None:
    """Emit ops for prop diffs on a node, including events and styles.

    Used by the patch path; both old and new props are static (already-
    resolved) values. For initial mount with potentially reactive prop
    values, use [`apply_initial_props`][wybthon.props.apply_initial_props].

    Args:
        node_id: The target node id.
        old_props: Previously-applied prop dict.
        new_props: Newly-resolved prop dict.
    """
    for name, old_val in old_props.items():
        if name in ("key", "ref"):
            continue
        if name not in new_props:
            _remove_single_prop(node_id, name, old_val)

    for name, new_val in new_props.items():
        if name in ("key", "ref"):
            continue
        old_val = old_props.get(name, _UNSET)
        # Skip untouched props. Identity covers handlers/getters; scalar
        # equality covers the common attribute case. `value`/`checked`
        # are always re-asserted because the live DOM property can
        # diverge from the last-applied prop (user input).
        if name not in ("value", "checked"):
            if old_val is new_val and old_val is not _UNSET:
                continue
            if isinstance(new_val, (str, int, float, bool)) and type(old_val) is type(new_val) and old_val == new_val:
                continue
        _apply_single_prop(node_id, name, old_val, new_val)


def apply_initial_props(node_id: int, new_props: PropsDict) -> None:
    """Emit ops for a fresh set of props on initial mount, wiring reactive bindings.

    Callable prop values (excluding event handlers and `ref`) are treated
    as **reactive bindings**: each is wrapped in its own effect so that
    updates re-apply only that single prop, with no re-render of the
    surrounding component. Static values are applied once.

    Args:
        node_id: The target node id.
        new_props: Initial prop dict.
    """
    for name, value in new_props.items():
        if name in ("key", "ref"):
            continue
        if is_event_prop(name):
            set_handler(node_id, name, value if callable(value) else None)
            continue
        if is_getter(value):
            _bind_reactive_prop(node_id, name, value)
        else:
            _apply_single_prop(node_id, name, _UNSET, value)


def _bind_reactive_prop(node_id: int, name: str, getter: Any) -> Any:
    """Wrap `getter` in an effect that re-applies prop `name` on changes.

    Returns the underlying `Computation` so callers can dispose it when
    the element unmounts.
    """
    from .reactivity import effect

    last: list = [_UNSET]

    def update() -> None:
        try:
            new_val = getter()
        except Exception as exc:
            log_error(f"Reactive prop '{name}' getter raised: {exc}", exc)
            return
        old_val = last[0]
        last[0] = new_val
        _apply_single_prop(node_id, name, old_val, new_val)

    return effect(update)


# ---------------------------------------------------------------------------
# Class / Style / Dataset helpers
# ---------------------------------------------------------------------------


def _class_string(value: Any) -> str:
    """Normalize a class prop (string, list, or dict) to a class string."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        return " ".join(str(x) for x in value if x)
    if isinstance(value, dict):
        # Accept {"name": truthy} mapping for conditional classes
        return " ".join(str(k) for k, v in value.items() if v)
    return str(value)


def _remove_styles(node_id: int, old_val: Any) -> None:
    """Emit ops removing previously applied inline styles."""
    if isinstance(old_val, dict) and old_val:
        kernel.emit((OP_SET_STYLE, node_id, {to_kebab(k): None for k in old_val}))


def _apply_style(node_id: int, old_val: Any, new_val: Any) -> None:
    """Diff style dicts and emit a single style op with the changes."""
    old_styles = old_val if isinstance(old_val, dict) else {}
    if isinstance(new_val, dict):
        decls: Dict[str, Optional[str]] = {}
        for sk in old_styles:
            if sk not in new_val:
                decls[to_kebab(sk)] = None
        for sk, sv in new_val.items():
            decls[to_kebab(sk)] = str(sv)
        if decls:
            kernel.emit((OP_SET_STYLE, node_id, decls))
    else:
        _remove_styles(node_id, old_styles)


def _remove_dataset(node_id: int, old_val: Any) -> None:
    """Emit ops removing previously applied data-* attributes."""
    if isinstance(old_val, dict):
        for dk in old_val:
            kernel.emit((OP_SET_ATTR, node_id, f"data-{dk}", None))


def _apply_dataset(node_id: int, old_val: Any, new_val: Any) -> None:
    """Diff and apply data-* attribute changes."""
    old_ds = old_val if isinstance(old_val, dict) else {}
    if isinstance(new_val, dict):
        for dk in old_ds:
            if dk not in new_val:
                kernel.emit((OP_SET_ATTR, node_id, f"data-{dk}", None))
        for dk, dv in new_val.items():
            kernel.emit((OP_SET_ATTR, node_id, f"data-{dk}", str(dv)))
    else:
        _remove_dataset(node_id, old_ds)
