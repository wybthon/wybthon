"""DOM property application and diffing for element VNodes.

Handles translating VNode props into DOM attribute/style/event mutations,
including controlled form elements (``value``, ``checked``), CSS style
objects, dataset attributes, and event handler delegation.
"""

from __future__ import annotations

import re
from typing import Any, Dict

from ._warnings import component_name, log_error
from .dom import Element
from .events import set_handler

__all__: list = []

PropsDict = Dict[str, Any]

CAMEL_TO_KEBAB = re.compile(r"(?<!^)(?=[A-Z])")


def to_kebab(name: str) -> str:
    """Convert camelCase style property names to kebab-case."""
    return CAMEL_TO_KEBAB.sub("-", name).lower()


def is_event_prop(name: str) -> bool:
    """Return True if a prop name is an event handler prop like on_click or onClick."""
    if name.startswith("on_"):
        return True
    return len(name) > 2 and name.startswith("on") and name[2].isupper()


def event_name_from_prop(name: str) -> str:
    """Map on_click/onClick style props to a DOM event name."""
    if name.startswith("on_"):
        return name[3:]
    if name.startswith("on"):
        return name[2:].lower()
    return name


def attach_ref(props: PropsDict, el: Element) -> None:
    """Set *ref.current* to *el* if a ``ref`` prop is present."""
    ref = props.get("ref")
    if ref is not None and hasattr(ref, "current"):
        ref.current = el


def detach_ref(props: PropsDict) -> None:
    """Clear *ref.current* if a ``ref`` prop is present."""
    ref = props.get("ref")
    if ref is not None and hasattr(ref, "current"):
        ref.current = None


def apply_props(el: Element, old_props: PropsDict, new_props: PropsDict) -> None:
    """Apply prop diffs to a concrete DOM element, including events and styles."""
    for name, old_val in list(old_props.items()):
        if name in ("key", "ref"):
            continue
        if name not in new_props:
            if is_event_prop(name):
                set_handler(el, name, None)
            elif name in ("class", "className"):
                el.set_attr("class", "")
            elif name == "style":
                _remove_styles(el, old_val)
            elif name == "dataset":
                _remove_dataset(el, old_val)
            elif name == "value":
                _set_dom_property(el, "value", "")
            elif name == "checked":
                _set_dom_property(el, "checked", False)
            else:
                el.remove_attr(name)

    for name, new_val in new_props.items():
        if name in ("key", "ref"):
            continue
        if is_event_prop(name):
            old_handler = old_props.get(name)
            if old_handler is new_val:
                continue
            set_handler(el, name, new_val if callable(new_val) else None)
            continue

        if name in ("class", "className"):
            _apply_class(el, new_val)
            continue

        if name == "style":
            _apply_style(el, old_props.get("style"), new_val)
            continue

        if name == "dataset":
            _apply_dataset(el, old_props.get("dataset"), new_val)
            continue

        if name == "value":
            _set_dom_property(el, "value", "" if new_val is None else str(new_val))
            continue

        if name == "checked":
            _set_dom_property(el, "checked", bool(new_val))
            continue

        el.set_attr(name, new_val)


def _apply_class(el: Element, value: Any) -> None:
    """Set the class attribute from a string, list, or other value."""
    class_str: str
    if value is None:
        class_str = ""
    elif isinstance(value, str):
        class_str = value
    elif isinstance(value, (list, tuple)):
        class_str = " ".join(str(x) for x in value if x)
    else:
        class_str = str(value)
    el.set_attr("class", class_str)


def _remove_styles(el: Element, old_val: Any) -> None:
    """Remove previously applied inline styles."""
    if isinstance(old_val, dict):
        style_obj = el.element.style
        for sk in old_val.keys():
            style_obj.removeProperty(to_kebab(sk))


def _apply_style(el: Element, old_val: Any, new_val: Any) -> None:
    """Diff and apply inline style changes."""
    style_obj = el.element.style
    old_styles = old_val if isinstance(old_val, dict) else {}
    if isinstance(new_val, dict):
        if isinstance(old_styles, dict):
            for sk in old_styles.keys():
                if sk not in new_val:
                    style_obj.removeProperty(to_kebab(sk))
        for sk, sv in new_val.items():
            style_obj.setProperty(to_kebab(sk), str(sv))
    else:
        if isinstance(old_styles, dict):
            for sk in old_styles.keys():
                style_obj.removeProperty(to_kebab(sk))


def _remove_dataset(el: Element, old_val: Any) -> None:
    """Remove previously applied data-* attributes."""
    if isinstance(old_val, dict):
        for dk in old_val.keys():
            el.remove_attr(f"data-{dk}")


def _apply_dataset(el: Element, old_val: Any, new_val: Any) -> None:
    """Diff and apply data-* attribute changes."""
    old_ds = old_val if isinstance(old_val, dict) else {}
    if isinstance(new_val, dict):
        if isinstance(old_ds, dict):
            for dk in old_ds.keys():
                if dk not in new_val:
                    el.remove_attr(f"data-{dk}")
        for dk, dv in new_val.items():
            el.set_attr(f"data-{dk}", dv)
    else:
        if isinstance(old_ds, dict):
            for dk in old_ds.keys():
                el.remove_attr(f"data-{dk}")


def _set_dom_property(el: Element, name: str, value: Any) -> None:
    """Set a DOM property (value/checked) with attribute fallback."""
    try:
        setattr(el.element, name, value)
    except Exception as exc:
        log_error(
            f"Failed to set DOM property '{name}' on {component_name(getattr(el, 'element', el))}: {exc}",
            exc,
        )
        if isinstance(value, bool):
            if value:
                el.set_attr(name, name)
            else:
                el.remove_attr(name)
        else:
            el.set_attr(name, "" if value is None else str(value))
