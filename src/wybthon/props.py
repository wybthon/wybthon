"""DOM property application and diffing for element VNodes.

Translates VNode props into batched DOM ops (see `wybthon.kernel`):

- **Attributes** with Pythonic names: `class_` and `html_for` map to
  `class` and `for`, and underscores become hyphens (`aria_label`,
  `data_id`, `stroke_width`).
- **Boolean attributes**: `True` sets the attribute, `False`/`None`
  removes it (`disabled=False` renders no attribute).
- **Controlled form elements** (`value`, `checked`) via DOM properties.
- **CSS style objects** (`{"background_color": "red"}` becomes
  `background-color: red`) or raw style strings.
- **Dataset attributes** (`{"dataset": {"id": 5}}` becomes `data-id="5"`).
- **Event delegation** for `on_click`-style handlers.
- **Refs**: a [`Ref`][wybthon.Ref], a callback `ref(el)`, or a list of
  either.
- **Reactive bindings**: an accessor or zero-arg function as a prop
  value (or as a `class`/`style` dict value) is wrapped in its own render
  effect so updates re-apply only that prop.

Nothing here touches the DOM directly; every applier emits ops against
an integer node id and the kernel applies the batch in one bridge
crossing at commit time. Application code never imports this module.
"""

from __future__ import annotations

import re
from typing import Any

from . import kernel
from ._warnings import log_error
from .events import set_handler
from .kernel import OP_SET_ATTR, OP_SET_PROP, OP_SET_STYLE
from .reactivity import _core
from .reactivity._core import _K_RENDER, Computation, NotReadyError, _unwrap, is_accessor

__all__: list[str] = []

PropsDict = dict[str, Any]

_CAMEL_TO_KEBAB = re.compile(r"(?<!^)(?=[A-Z])")

# Sentinel for "no previous value" in reactive bindings / initial apply.
_UNSET = object()
# Sentinel a binding's compute stage returns to keep the current DOM value.
_KEEP = object()

# Props the element applier never writes to the DOM.
_SKIP = frozenset({"key", "ref", "children"})

# Props written as DOM properties rather than attributes.
_DOM_PROPS = frozenset({"value", "checked", "inner_html", "innerHTML"})

# HTML boolean attributes: present/absent, never "true"/"false".
_BOOLEAN_ATTRS = frozenset(
    {
        "allowfullscreen",
        "async",
        "autofocus",
        "autoplay",
        "checked",
        "controls",
        "default",
        "defer",
        "disabled",
        "formnovalidate",
        "hidden",
        "inert",
        "ismap",
        "itemscope",
        "loop",
        "multiple",
        "muted",
        "nomodule",
        "novalidate",
        "open",
        "playsinline",
        "readonly",
        "required",
        "reversed",
        "seamless",
        "selected",
    }
)

# Per-node reactive prop bindings: node_id -> {prop name: computation}.
_bindings: dict[int, dict[str, Computation]] = {}


def to_kebab(name: str) -> str:
    """Convert a camelCase or snake_case CSS property name to kebab-case."""
    if "_" in name:
        return name.replace("_", "-")
    return _CAMEL_TO_KEBAB.sub("-", name).lower()


def attr_name(name: str) -> str:
    """Map a Pythonic prop name to its DOM attribute name.

    `class_` becomes `class`, `html_for` and `for_` become `for`, and any
    other name containing underscores has them replaced with hyphens
    (`aria_label`, `stroke_width`, `data_testid`).
    """
    if name == "class_":
        return "class"
    if name == "html_for" or name == "for_":
        return "for"
    if "_" in name:
        return name.replace("_", "-")
    return name


def is_event_prop(name: str) -> bool:
    """Return True for `on_click`-style (or `onClick`-style) handler props."""
    if name.startswith("on_"):
        return True
    return len(name) > 2 and name.startswith("on") and name[2].isupper()


def event_name_from_prop(name: str) -> str:
    """Convert an `on_click` / `onClick` prop name to its DOM event name."""
    if name.startswith("on_"):
        return name[3:]
    if name.startswith("on"):
        return name[2:].lower()
    return name


# ---------------------------------------------------------------------------
# Refs
# ---------------------------------------------------------------------------


def attach_ref(props: PropsDict, node_id: int) -> None:
    """Assign the mounted element to the `ref` prop (Ref, callback, or list)."""
    ref = props.get("ref")
    if ref is None:
        return
    from .dom import Element

    _assign_ref(ref, Element(node_id=node_id))


def _assign_ref(ref: Any, element: Any) -> None:
    if isinstance(ref, (list, tuple)):
        for r in ref:
            _assign_ref(r, element)
        return
    if hasattr(ref, "current"):
        ref.current = element
        return
    if callable(ref):
        try:
            ref(element)
        except Exception as exc:
            log_error(f"ref callback raised: {exc}", exc)


def detach_ref(props: PropsDict) -> None:
    """Reset `Ref` objects in the `ref` prop to `None` (callbacks aren't re-invoked)."""
    ref = props.get("ref")
    if ref is None:
        return
    _clear_ref(ref)


def _clear_ref(ref: Any) -> None:
    if isinstance(ref, (list, tuple)):
        for r in ref:
            _clear_ref(r)
        return
    if hasattr(ref, "current"):
        ref.current = None


# ---------------------------------------------------------------------------
# Single-prop appliers
# ---------------------------------------------------------------------------


def _apply_single_prop(node_id: int, name: str, old_val: Any, new_val: Any) -> None:
    """Emit ops applying (or diffing) one prop on a DOM node.

    `old_val` may be `_UNSET` for an initial application, in which case
    the prop is written unconditionally.
    """
    if name in _SKIP:
        return

    if is_event_prop(name):
        if old_val is not _UNSET and old_val is new_val:
            return
        set_handler(node_id, name, new_val if callable(new_val) else None)
        return

    if name == "class" or name == "class_":
        kernel.emit((OP_SET_ATTR, node_id, "class", _class_string(new_val) or None))
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

    if name == "inner_html" or name == "innerHTML":
        kernel.emit((OP_SET_PROP, node_id, "innerHTML", "" if new_val is None else str(new_val)))
        return

    attr = attr_name(name)
    if new_val is None or new_val is False:
        kernel.emit((OP_SET_ATTR, node_id, attr, None))
        return
    if new_val is True:
        kernel.emit((OP_SET_ATTR, node_id, attr, "" if attr in _BOOLEAN_ATTRS else "true"))
        return
    kernel.emit((OP_SET_ATTR, node_id, attr, str(new_val)))


def _remove_single_prop(node_id: int, name: str, old_val: Any) -> None:
    """Emit ops removing one prop from a DOM node."""
    if name in _SKIP:
        return
    if is_event_prop(name):
        set_handler(node_id, name, None)
    elif name == "class" or name == "class_":
        kernel.emit((OP_SET_ATTR, node_id, "class", None))
    elif name == "style":
        _remove_styles(node_id, old_val)
    elif name == "dataset":
        _remove_dataset(node_id, old_val)
    elif name == "value":
        kernel.emit((OP_SET_PROP, node_id, "value", ""))
    elif name == "checked":
        kernel.emit((OP_SET_PROP, node_id, "checked", False))
    elif name == "inner_html" or name == "innerHTML":
        kernel.emit((OP_SET_PROP, node_id, "innerHTML", ""))
    else:
        kernel.emit((OP_SET_ATTR, node_id, attr_name(name), None))


def _reactive_dict(value: Any) -> bool:
    """Return True when `value` is a dict with at least one reactive value."""
    if type(value) is not dict:
        return False
    for v in value.values():
        if is_accessor(v):
            return True
    return False


def _dict_getter(value: dict[str, Any]) -> Any:
    def getter() -> dict[str, Any]:
        return {k: _unwrap(v) for k, v in value.items()}

    return getter


def binding_value(name: str, value: Any) -> Any:
    """Return the reactive expression for a prop value, or `None` when it's static.

    A prop is reactive when its value is an accessor or zero-arg
    function, or (for `class` and `style`) a dict containing one.
    """
    if name in _SKIP or is_event_prop(name):
        return None
    if is_accessor(value):
        return value
    if (name == "class" or name == "class_" or name == "style") and _reactive_dict(value):
        return _dict_getter(value)
    return None


# ---------------------------------------------------------------------------
# Bulk appliers
# ---------------------------------------------------------------------------


def apply_initial_props(node_id: int, new_props: PropsDict) -> None:
    """Emit ops for a fresh element's props, wiring reactive bindings."""
    for name, value in new_props.items():
        if name in _SKIP:
            continue
        if is_event_prop(name):
            set_handler(node_id, name, value if callable(value) else None)
            continue
        getter = binding_value(name, value)
        if getter is not None:
            _bind_reactive_prop(node_id, name, getter)
        else:
            _apply_single_prop(node_id, name, _UNSET, value)


def apply_props(node_id: int, old_props: PropsDict, new_props: PropsDict) -> None:
    """Emit ops for prop diffs on an existing node (the patch path).

    Reactive values that are the same object on both sides are left
    alone (their binding keeps running); a new reactive value replaces
    the previous binding; a static value replaces a binding with a
    plain write.
    """
    for name, old_val in old_props.items():
        if name in _SKIP:
            continue
        if name not in new_props:
            _unbind(node_id, name)
            _remove_single_prop(node_id, name, old_val)

    for name, new_val in new_props.items():
        if name in _SKIP:
            continue
        old_val = old_props.get(name, _UNSET)
        if is_event_prop(name):
            if old_val is not new_val:
                set_handler(node_id, name, new_val if callable(new_val) else None)
            continue
        if old_val is new_val and old_val is not _UNSET and name != "value" and name != "checked":
            continue
        getter = binding_value(name, new_val)
        if getter is not None:
            if old_val is new_val:
                continue
            _unbind(node_id, name)
            _bind_reactive_prop(node_id, name, getter)
            continue
        if _unbind(node_id, name):
            old_val = _UNSET
        # `value`/`checked` are always re-asserted: the live DOM property
        # may have diverged from the last-applied prop (user input).
        if name != "value" and name != "checked":
            if isinstance(new_val, (str, int, float, bool)) and type(old_val) is type(new_val) and old_val == new_val:
                continue
        _apply_single_prop(node_id, name, old_val, new_val)


def _unbind(node_id: int, name: str) -> bool:
    table = _bindings.get(node_id)
    if table is None:
        return False
    comp = table.pop(name, None)
    if not table:
        _bindings.pop(node_id, None)
    if comp is None:
        return False
    comp.dispose()
    return True


def remove_bindings_for(node_id: int) -> None:
    """Dispose every reactive prop binding on `node_id` (called on unmount)."""
    table = _bindings.pop(node_id, None)
    if table:
        for comp in table.values():
            comp.dispose()


def _bind_reactive_prop(node_id: int, name: str, getter: Any) -> Computation:
    """Wrap `getter` in a render effect that re-applies prop `name` on change.

    Render-phase scheduling means every dirty binding in a flush emits
    its op before the single DOM commit. Errors route to the nearest
    [`Errored`][wybthon.Errored] boundary, or are logged.
    """

    def compute() -> Any:
        try:
            return getter()
        except NotReadyError:
            return _KEEP
        except Exception as exc:
            from .reconciler import _dispatch_to_error_boundary

            if not _dispatch_to_error_boundary(exc):
                log_error(f"Reactive prop '{name}' raised: {exc}", exc)
            return _KEEP

    last: list[Any] = [_UNSET]

    def apply(new_val: Any) -> None:
        if new_val is _KEEP:
            return
        old_val = last[0]
        last[0] = new_val
        _apply_single_prop(node_id, name, old_val, new_val)

    comp = Computation(compute, kind=_K_RENDER, apply=apply, pass_prev=False)
    owner = _core._current_owner
    if owner is not None:
        owner._add_child(comp)
    table = _bindings.get(node_id)
    if table is None:
        _bindings[node_id] = {name: comp}
    else:
        table[name] = comp
    comp._update_if_necessary()
    return comp


# ---------------------------------------------------------------------------
# Class / style / dataset helpers
# ---------------------------------------------------------------------------


def _class_string(value: Any) -> str:
    """Normalize a class prop (string, list, or dict) to a class string."""
    if value is None or value is False:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        return " ".join(str(x) for x in value if x)
    if isinstance(value, dict):
        return " ".join(str(k) for k, v in value.items() if v)
    return str(value)


def _remove_styles(node_id: int, old_val: Any) -> None:
    if isinstance(old_val, dict) and old_val:
        kernel.emit((OP_SET_STYLE, node_id, {to_kebab(k): None for k in old_val}))
    elif isinstance(old_val, str):
        kernel.emit((OP_SET_ATTR, node_id, "style", None))


def _apply_style(node_id: int, old_val: Any, new_val: Any) -> None:
    """Diff style dicts (or set a raw style string) with a single op."""
    if isinstance(new_val, str):
        if old_val != new_val:
            kernel.emit((OP_SET_ATTR, node_id, "style", new_val))
        return
    if isinstance(old_val, str):
        kernel.emit((OP_SET_ATTR, node_id, "style", None))
        old_val = None
    old_styles = old_val if isinstance(old_val, dict) else {}
    if isinstance(new_val, dict):
        decls: dict[str, str | None] = {}
        for sk in old_styles:
            if sk not in new_val:
                decls[to_kebab(sk)] = None
        for sk, sv in new_val.items():
            if sv is None or sv is False:
                decls[to_kebab(sk)] = None
            elif old_styles.get(sk, _UNSET) != sv:
                decls[to_kebab(sk)] = str(sv)
        if decls:
            kernel.emit((OP_SET_STYLE, node_id, decls))
    else:
        _remove_styles(node_id, old_styles)


def _remove_dataset(node_id: int, old_val: Any) -> None:
    if isinstance(old_val, dict):
        for dk in old_val:
            kernel.emit((OP_SET_ATTR, node_id, f"data-{to_kebab(str(dk))}", None))


def _apply_dataset(node_id: int, old_val: Any, new_val: Any) -> None:
    old_ds = old_val if isinstance(old_val, dict) else {}
    if isinstance(new_val, dict):
        for dk in old_ds:
            if dk not in new_val:
                kernel.emit((OP_SET_ATTR, node_id, f"data-{to_kebab(str(dk))}", None))
        for dk, dv in new_val.items():
            if dv is None or dv is False:
                kernel.emit((OP_SET_ATTR, node_id, f"data-{to_kebab(str(dk))}", None))
            elif old_ds.get(dk, _UNSET) != dv:
                kernel.emit((OP_SET_ATTR, node_id, f"data-{to_kebab(str(dk))}", "" if dv is True else str(dv)))
    else:
        _remove_dataset(node_id, old_ds)
