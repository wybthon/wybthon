"""Delegated event handling for the batched renderer.

Event delegation lives in the rendering kernel: one native listener per
event type is installed on `document`, walks the ancestor chain of the
event target natively, and calls into Python once per matched handler.
The call carries a small JSON payload (event type, target value/checked
state, key, mouse buttons, modifiers), so the common handler patterns
(`evt.target.value`, `evt.key`, `evt.prevent_default()`) never touch a
`JsProxy` at all.

Registering a handler is itself a batched op (`LISTEN`), so mounting a
list with thousands of handlers adds nothing to the bridge-crossing
count.

Public surface:

- [`DomEvent`][wybthon.DomEvent]: the event object passed to handlers,
  exposing `type`, `target`, `current_target`, key and mouse fields,
  and helpers like [`prevent_default`][wybthon.DomEvent.prevent_default]
  and [`stop_propagation`][wybthon.DomEvent.stop_propagation].

The remaining helpers are internal:
[`set_handler`][wybthon.events.set_handler] and
[`remove_handlers_for`][wybthon.events.remove_handlers_for] are called
by the renderer, and [`dispatch_event`][wybthon.events.dispatch_event]
is the entry point the kernel invokes when a native event fires.

See Also:
    - [Forms guide](../concepts/forms.md)
"""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, Optional

from . import kernel
from ._warnings import log_error

__all__ = ["DomEvent"]


# Per-node handler tables: node_id -> {event_type: handler}.
_handlers: Dict[int, Dict[str, Callable]] = {}


def _event_prop_to_type(name: str) -> str:
    """Normalize a prop name like `on_click` or `onClick` to a plain event type.

    Args:
        name: Prop key as seen on a `VNode` (e.g., `"on_click"`).

    Returns:
        The lower-cased event type (e.g., `"click"`).
    """
    if name.startswith("on_"):
        return name[3:]
    if name.startswith("on"):
        return name[2:].lower()
    return name


class _EventTarget:
    """Payload-backed view of the event target.

    Exposes the fields handlers actually read (`value`, `checked`)
    straight from the dispatch payload, with no bridge crossing. The
    raw DOM node is available through `element` as an escape hatch and
    is materialized on first access.
    """

    __slots__ = ("_payload", "_element")

    def __init__(self, payload: Dict[str, Any]) -> None:
        self._payload = payload
        self._element: Any = None

    @property
    def value(self) -> Any:
        """The target's `value` at dispatch time (inputs, selects, textareas)."""
        return self._payload.get("value")

    @property
    def checked(self) -> bool:
        """The target's `checked` state at dispatch time."""
        return bool(self._payload.get("checked"))

    @property
    def element(self) -> Any:
        """The raw target node (escape hatch; may cross the bridge once)."""
        if self._element is None:
            target_id = self._payload.get("targetId")
            if target_id is not None:
                self._element = kernel.get_node(target_id)
            else:
                raw = kernel.current_event()
                self._element = getattr(raw, "target", None) if raw is not None else None
        return self._element

    @property
    def files(self) -> Any:
        """`FileList` for file inputs, fetched from the raw node."""
        return getattr(self.element, "files", None)


class DomEvent:
    """The event object Wybthon passes to delegated handlers.

    Built from the kernel's dispatch payload rather than a `JsProxy`,
    so reading it is free of bridge crossings. Use
    [`raw`][wybthon.DomEvent.raw] to reach the native event object for
    anything not covered by the payload.

    Attributes:
        type: Event type string (e.g., `"click"`).
        target: Payload-backed view of the original event target,
            exposing `value`, `checked`, `files`, and `element`.
        current_target: The element whose handler is currently running
            (an id-backed [`Element`][wybthon.Element]).
        key: `KeyboardEvent.key`, or `None` for non-keyboard events.
        code: `KeyboardEvent.code`, or `None`.
        alt_key: Whether Alt was held.
        ctrl_key: Whether Ctrl was held.
        meta_key: Whether Meta/Cmd was held.
        shift_key: Whether Shift was held.
        button: `MouseEvent.button` (0 for primary).
        client_x: Pointer x position, when applicable.
        client_y: Pointer y position, when applicable.
    """

    __slots__ = (
        "type",
        "target",
        "current_target",
        "key",
        "code",
        "alt_key",
        "ctrl_key",
        "meta_key",
        "shift_key",
        "button",
        "client_x",
        "client_y",
        "_stopped",
        "_default_prevented",
    )

    def __init__(self, payload: Dict[str, Any], current_target: Optional[Any] = None) -> None:
        """Build an event from a dispatch payload dict.

        Args:
            payload: Parsed dispatch payload from the kernel.
            current_target: The [`Element`][wybthon.Element] whose
                handler is being invoked.
        """
        self.type = payload.get("type")
        self.target = _EventTarget(payload)
        self.current_target = current_target
        self.key = payload.get("key")
        self.code = payload.get("code")
        self.alt_key = bool(payload.get("altKey"))
        self.ctrl_key = bool(payload.get("ctrlKey"))
        self.meta_key = bool(payload.get("metaKey"))
        self.shift_key = bool(payload.get("shiftKey"))
        self.button = payload.get("button", 0)
        self.client_x = payload.get("clientX", 0)
        self.client_y = payload.get("clientY", 0)
        self._stopped = False
        self._default_prevented = False

    @property
    def raw(self) -> Any:
        """The native browser event object (escape hatch).

        Only valid synchronously during dispatch; returns `None`
        afterwards.
        """
        return kernel.current_event()

    def prevent_default(self) -> None:
        """Prevent the default browser action for this event."""
        self._default_prevented = True

    def stop_propagation(self) -> None:
        """Stop the delegated dispatch from walking further up the tree.

        Also stops native propagation so other JS listeners above don't
        fire.
        """
        self._stopped = True


def set_handler(node_id: int, event_prop_name: str, handler: Optional[Callable]) -> None:
    """Attach, update, or remove a handler for an event property on a node.

    Registration is batched: the kernel-side `LISTEN`/`UNLISTEN` ops
    ride the same command buffer as the DOM mutations, so wiring
    handlers costs no extra bridge crossings.

    Args:
        node_id: Kernel node id to attach to.
        event_prop_name: Prop name as seen on the `VNode` (e.g.
            `"on_click"`); normalized to the underlying DOM event type
            (`"on_click"` → `"click"`).
        handler: Callback to invoke. Pass `None` to remove an existing
            handler for this event type on this node.
    """
    event_type = _event_prop_to_type(event_prop_name)
    mapping = _handlers.get(node_id)

    if handler is None:
        if mapping is not None and event_type in mapping:
            del mapping[event_type]
            if not mapping:
                _handlers.pop(node_id, None)
            kernel.emit((kernel.OP_UNLISTEN, node_id, event_type))
        return

    if mapping is None:
        mapping = {}
        _handlers[node_id] = mapping
    had_previous = event_type in mapping
    mapping[event_type] = handler
    if not had_previous:
        kernel.emit((kernel.OP_LISTEN, node_id, event_type))


def remove_handlers_for(node_id: int) -> None:
    """Drop every handler registered for `node_id` (Python side only).

    Called by the renderer during unmount. The kernel-side listener
    bookkeeping is cleared by the `RELEASE` op that accompanies the
    subtree removal, so no per-handler ops are needed.
    """
    _handlers.pop(node_id, None)


def dispatch_event(node_id: int, event_type: str, payload_json: str) -> int:
    """Invoke the handler for `(node_id, event_type)` with a payload.

    This is the entry point the kernel's native root listener calls,
    once per matched node while walking the ancestor chain.

    Args:
        node_id: Id of the node whose handler should run.
        event_type: DOM event type (e.g., `"click"`).
        payload_json: JSON-encoded payload built natively by the kernel.

    Returns:
        Flag bits for the kernel: bit 1 stops the delegated walk and
        native propagation, bit 2 calls `preventDefault`.
    """
    mapping = _handlers.get(node_id)
    handler = mapping.get(event_type) if mapping is not None else None
    if handler is None:
        return 0

    payload = json.loads(payload_json) if isinstance(payload_json, str) else dict(payload_json)

    from .dom import Element

    evt = DomEvent(payload, current_target=Element(node_id=node_id))
    try:
        handler(evt)
    except Exception as exc:
        log_error(f"Event handler for '{event_type}' raised: {exc}", exc)
    kernel.commit()

    flags = 0
    if evt._stopped:
        flags |= kernel.FLAG_STOP_PROPAGATION
    if evt._default_prevented:
        flags |= kernel.FLAG_PREVENT_DEFAULT
    return flags


kernel.set_event_dispatcher(dispatch_event)
