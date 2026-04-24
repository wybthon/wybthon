"""DOM property application and diffing for element VNodes.

Translates VNode props into DOM attribute, style, and event mutations,
including:

- **Controlled form elements** (`value`, `checked`) via DOM properties.
- **CSS style objects** (`{"backgroundColor": "red"}` → kebab-cased
  inline styles).
- **Dataset attributes** (`{"dataset": {"id": 5}}` → `data-id="5"`).
- **Event delegation** for `on_click` / `onClick` style handlers.
- **Reactive prop bindings**: callable prop values are wrapped in their
  own effect so updates re-apply only the affected prop, never the
  surrounding component.

This module is consumed by the reconciler; most application code never
imports from it directly.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

from ._warnings import component_name, log_error
from .dom import Element
from .events import set_handler
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
        The kebab-cased equivalent (e.g. `"background-color"`).
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
        The DOM event name (e.g. `"click"`, `"mouseover"`).
    """
    if name.startswith("on_"):
        return name[3:]
    if name.startswith("on"):
        return name[2:].lower()
    return name


def attach_ref(props: PropsDict, el: Element) -> None:
    """Assign `el` to `props["ref"].current` when a `ref` prop is present."""
    ref = props.get("ref")
    if ref is not None and hasattr(ref, "current"):
        ref.current = el


def detach_ref(props: PropsDict) -> None:
    """Clear `props["ref"].current` when a `ref` prop is present."""
    ref = props.get("ref")
    if ref is not None and hasattr(ref, "current"):
        ref.current = None


# ---------------------------------------------------------------------------
# Per-prop appliers (used by both initial mount and per-prop reactive bindings)
# ---------------------------------------------------------------------------


def _apply_single_prop(el: Element, name: str, old_val: Any, new_val: Any) -> None:
    """Apply (or diff) a single prop on a real DOM element.

    `old_val` may be the sentinel `_UNSET` for an initial application; in
    that case the prop is written unconditionally with no diff against
    a previous value.
    """
    if name in ("key", "ref"):
        return

    if is_event_prop(name):
        if old_val is not _UNSET and old_val is new_val:
            return
        set_handler(el, name, new_val if callable(new_val) else None)
        return

    if name in ("class", "className"):
        _apply_class(el, new_val)
        return

    if name == "style":
        _apply_style(el, None if old_val is _UNSET else old_val, new_val)
        return

    if name == "dataset":
        _apply_dataset(el, None if old_val is _UNSET else old_val, new_val)
        return

    if name == "value":
        _set_dom_property(el, "value", "" if new_val is None else str(new_val))
        return

    if name == "checked":
        _set_dom_property(el, "checked", bool(new_val))
        return

    el.set_attr(name, new_val)


def _remove_single_prop(el: Element, name: str, old_val: Any) -> None:
    """Remove a single prop from a real DOM element."""
    if name in ("key", "ref"):
        return
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


# ---------------------------------------------------------------------------
# Bulk appliers
# ---------------------------------------------------------------------------


def apply_props(el: Element, old_props: PropsDict, new_props: PropsDict) -> None:
    """Apply prop diffs to a concrete DOM element, including events and styles.

    Used by the patch path; both old and new props are static (already-
    resolved) values. For initial mount with potentially reactive prop
    values, use [`apply_initial_props`][wybthon.props.apply_initial_props].

    Args:
        el: The target DOM element wrapper.
        old_props: Previously-applied prop dict.
        new_props: Newly-resolved prop dict.
    """
    for name, old_val in list(old_props.items()):
        if name in ("key", "ref"):
            continue
        if name not in new_props:
            _remove_single_prop(el, name, old_val)

    for name, new_val in new_props.items():
        if name in ("key", "ref"):
            continue
        old_val = old_props.get(name, _UNSET)
        _apply_single_prop(el, name, old_val, new_val)


def apply_initial_props(el: Element, new_props: PropsDict, owner_vnode: Optional[Any] = None) -> None:
    """Apply a fresh set of props on initial mount, wiring reactive bindings.

    Callable prop values (excluding event handlers and `ref`) are treated
    as **reactive bindings**: each is wrapped in its own effect so that
    updates re-apply only that single prop, with no re-render of the
    surrounding component. Static values are applied once.

    Args:
        el: The target DOM element wrapper.
        new_props: Initial prop dict.
        owner_vnode: Currently unused. Accepted for forward compatibility
            with reconciler bookkeeping.
    """
    from .reactivity import _current_owner, effect

    for name, value in new_props.items():
        if name in ("key", "ref"):
            continue
        if is_event_prop(name):
            set_handler(el, name, value if callable(value) else None)
            continue
        if is_getter(value):
            _bind_reactive_prop(el, name, value)
        else:
            _apply_single_prop(el, name, _UNSET, value)

    # Re-export to silence unused-import warnings if this function is
    # invoked outside an active reactive scope.
    _ = (_current_owner, effect)


def _bind_reactive_prop(el: Element, name: str, getter: Any) -> Any:
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
        _apply_single_prop(el, name, old_val, new_val)

    return effect(update)


# ---------------------------------------------------------------------------
# Class / Style / Dataset helpers (unchanged; used by single-prop appliers)
# ---------------------------------------------------------------------------


def _apply_class(el: Element, value: Any) -> None:
    """Set the class attribute from a string, list, or other value."""
    class_str: str
    if value is None:
        class_str = ""
    elif isinstance(value, str):
        class_str = value
    elif isinstance(value, (list, tuple)):
        class_str = " ".join(str(x) for x in value if x)
    elif isinstance(value, dict):
        # Accept {"name": truthy} mapping for conditional classes
        class_str = " ".join(str(k) for k, v in value.items() if v)
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
