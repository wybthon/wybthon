"""Delegated event handling for the batched renderer.

Event delegation lives in the rendering kernel: one native listener per
event type is installed on each render root (the container passed to
[`render`][wybthon.render], plus any [`Portal`][wybthon.Portal] target),
walks the ancestor chain of the event target natively, and calls into
Python once for the bubbling route. Non-bubbling events and explicit native
listener options use direct listeners.
The call carries a small JSON payload (event type, target value/checked
state, key, mouse buttons, modifiers), so the common handler patterns
(`evt.target.value`, `evt.key`, `evt.prevent_default()`) never touch a
`JsProxy` at all.

Registering a handler costs no bridge crossing: a template declares its
delegated listeners when it's registered, so cloning a row marks them
natively, and other handlers ride the same command buffer as the DOM
mutations (`LISTEN`).

A handler may take the [`DomEvent`][wybthon.DomEvent] or no arguments
at all: `on_click=lambda: set_open(False)`.

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

import inspect
import json
from collections.abc import Callable
from dataclasses import dataclass
from types import FunctionType, MethodType
from typing import Any

from . import kernel
from ._warnings import log_error
from .reactivity import _core

__all__ = ["DomEvent", "EventHandler", "event"]


@dataclass(frozen=True, slots=True)
class EventHandler:
    """A handler with native listener options, constructed with ``event``."""

    callback: Callable[..., Any]
    capture: bool = False
    passive: bool = False
    once: bool = False

    def __call__(self, value: Any) -> Any:
        """Invoke the wrapped callback."""
        return self.callback(value)


def event(
    handler: Callable[..., Any], *, capture: bool = False, passive: bool = False, once: bool = False
) -> EventHandler:
    """Configure a native listener. Ordinary handlers use batched delegation."""
    return EventHandler(handler, capture, passive, once)


def _takes_event(callback: Callable[..., Any]) -> bool:
    """Whether a handler accepts the event argument (checked once, at registration)."""
    if type(callback) is FunctionType:
        code = callback.__code__
        return code.co_argcount > 0 or bool(code.co_flags & inspect.CO_VARARGS)
    if isinstance(callback, MethodType):
        code = getattr(callback.__func__, "__code__", None)
        if code is not None:
            return code.co_argcount > 1 or bool(code.co_flags & inspect.CO_VARARGS)
    try:
        params = inspect.signature(callback).parameters.values()
    except TypeError, ValueError:
        return True
    return any(
        p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD, p.VAR_POSITIONAL)
        for p in params
    )


class _Handler:
    __slots__ = ("callback", "owner", "options", "prop", "task_owner", "fired", "takes_event")

    def __init__(
        self, callback: Callable[..., Any], owner: _core.Owner | None, options: EventHandler | None, prop: str
    ) -> None:
        self.callback = callback
        self.owner = owner
        self.options = options
        self.prop = prop
        self.task_owner: _core.Owner | None = None
        self.fired = False
        self.takes_event = _takes_event(callback)


_handlers: dict[int, dict[str, _Handler]] = {}

# Event types that don't bubble get a direct native listener on their node.
NON_BUBBLING = frozenset(
    {
        "focus",
        "blur",
        "mouseenter",
        "mouseleave",
        "pointerenter",
        "pointerleave",
        "scroll",
        "load",
        "error",
        "invalid",
        "toggle",
    }
)

_event_keys: dict[str, str] = {}


def _event_key(name: str) -> str:
    """Map a handler prop name to its event key (memoized).

    `on_click` and `onClick` become `"click"`; a `_capture` suffix
    (`on_click_capture`) becomes `"click:capture"`.
    """
    key = _event_keys.get(name)
    if key is None:
        if name.startswith("on_"):
            key = name[3:]
        elif name.startswith("on"):
            key = name[2:].lower()
        else:
            key = name
        if key.endswith("_capture"):
            key = key[:-8] + ":capture"
        if len(_event_keys) < 4096:
            _event_keys[name] = key
    return key


def bind_delegated(node_id: int, key: str, prop: str, callback: Any) -> None:
    """Record a delegated handler whose listener the node's template already declared."""
    if callback is None:
        return
    handler = _Handler(callback, _core._current_owner, None, prop)
    mapping = _handlers.get(node_id)
    if mapping is None:
        _handlers[node_id] = {key: handler}
    else:
        mapping[key] = handler


class _EventTarget:
    """Payload-backed view of the event target.

    Exposes the fields handlers actually read (`value`, `checked`)
    straight from the dispatch payload, with no bridge crossing. The
    raw DOM node is available through `element` as an escape hatch and
    is materialized on first access.
    """

    __slots__ = ("_payload", "_element")

    def __init__(self, payload: dict[str, Any]) -> None:
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
    def scroll_top(self) -> float:
        """Vertical scroll offset captured at dispatch time."""
        return float(self._payload.get("scrollTop", 0))

    @property
    def selected_values(self) -> list[str]:
        """Selected option values, captured without a DOM read."""
        return self._payload.get("selectedValues", [])

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
        "detail",
        "is_composing",
        "_passive",
    )

    def __init__(self, payload: dict[str, Any], current_target: Any | None = None) -> None:
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
        self._default_prevented = bool(payload.get("defaultPrevented", False))
        self.detail = payload.get("detail")
        self.is_composing = bool(payload.get("isComposing", False))
        self._passive = False

    @property
    def raw(self) -> Any:
        """The native browser event object (escape hatch).

        Only valid synchronously during dispatch; returns `None`
        afterwards.
        """
        return kernel.current_event()

    def prevent_default(self) -> None:
        """Prevent the default browser action for this event."""
        if not self._passive:
            self._default_prevented = True

    def stop_propagation(self) -> None:
        """Stop the delegated dispatch from walking further up the tree.

        Also stops native propagation so other JS listeners above don't
        fire.
        """
        self._stopped = True


def set_handler(node_id: int, event_prop_name: str, handler: Callable[..., Any] | None) -> None:
    """Attach, update, or remove a handler for an event property on a node.

    Registration is batched: the kernel-side `LISTEN`/`UNLISTEN` ops
    ride the same command buffer as the DOM mutations, so wiring
    handlers costs no extra bridge crossings.

    Args:
        node_id: Kernel node id to attach to.
        event_prop_name: Prop name as seen on the `VNode` (e.g.
            `"on_click"`); normalized to the underlying DOM event type
            (`"on_click"` → `"click"`).
        handler: Callback to invoke, with the event or no arguments.
            Pass `None` to remove an existing handler for this event
            type on this node.
    """
    key = _event_key(event_prop_name)
    capture = key.endswith(":capture")
    options = handler if isinstance(handler, EventHandler) else None
    if options is not None and options.capture and not capture:
        key += ":capture"
        capture = True
    mapping = _handlers.get(node_id)
    previous_key = (
        next((name for name, item in mapping.items() if item.prop == event_prop_name), key) if mapping else key
    )
    previous = mapping.pop(previous_key, None) if mapping is not None else None
    if previous is not None:
        if previous.task_owner is not None:
            previous.task_owner.dispose()
        kernel.emit((kernel.OP_UNLISTEN, node_id, previous_key))
    if handler is None:
        if mapping is not None and not mapping:
            _handlers.pop(node_id, None)
        return
    if mapping is None:
        mapping = _handlers[node_id] = {}
    callback = options.callback if options is not None else handler
    mapping[key] = _Handler(callback, _core._current_owner, options, event_prop_name)
    if capture or (options is not None and (options.passive or options.once)):
        passive = options is not None and options.passive
        once = options is not None and options.once
        kernel.emit((kernel.OP_LISTEN, node_id, key, {"capture": capture, "passive": passive, "once": once}))
    else:
        kernel.emit((kernel.OP_LISTEN, node_id, key))


def remove_handlers_for(node_id: int) -> None:
    """Drop every handler registered for `node_id` (Python side only).

    Called by the renderer during unmount. The kernel-side listener
    bookkeeping is cleared by the `RELEASE` op that accompanies the
    subtree removal, so no per-handler ops are needed.
    """
    mapping = _handlers.pop(node_id, None)
    if mapping:
        for handler in mapping.values():
            if handler.task_owner is not None:
                handler.task_owner.dispose()


def dispatch_event(node_id: int, event_type: str, payload_json: str) -> int:
    """Invoke the handler for `(node_id, event_type)` with a payload.

    This is the entry point the kernel's native root listener calls,
    once for the matching bubbling route, or once for a direct native listener.

    Args:
        node_id: Id of the node whose handler should run.
        event_type: DOM event type (e.g., `"click"`).
        payload_json: JSON-encoded payload built natively by the kernel.

    Returns:
        Flag bits for the kernel: bit 1 stops the delegated walk and
        native propagation, bit 2 calls `preventDefault`.
    """
    payload = json.loads(payload_json) if isinstance(payload_json, str) else dict(payload_json)
    route = payload.get("route", [[node_id, event_type]])
    from .dom import Element

    evt = DomEvent(payload)
    for current_id, key in route:
        mapping = _handlers.get(current_id)
        handler = mapping.get(key) if mapping is not None else None
        if handler is None or (handler.owner is not None and handler.owner._disposed) or handler.fired:
            continue
        prevented = evt._default_prevented
        evt = DomEvent(payload, current_target=Element(node_id=current_id))
        evt._default_prevented = prevented
        options = handler.options
        evt._passive = options is not None and options.passive
        if options is not None and options.once:
            handler.fired = True
            # Keep the owner until its async body settles or the element unmounts.
            # Removing the native listener prevents later events reaching it.
            kernel.emit((kernel.OP_UNLISTEN, current_id, key))
        try:
            if handler.takes_event:
                result = _core._run_owned_untracked(handler.owner, lambda: handler.callback(evt))
            else:
                result = _core._run_owned_untracked(handler.owner, handler.callback)
            if inspect.isawaitable(result):
                if handler.task_owner is None:
                    handler.task_owner = _core.Owner()
                    if handler.owner is not None:
                        handler.owner._add_child(handler.task_owner)

                def alive(owner: _core.Owner = handler.task_owner) -> bool:
                    return not owner._disposed

                _core._drive_coroutine(
                    result,
                    owner=handler.task_owner,
                    observer=None,
                    alive=alive,
                    on_done=lambda _: None,
                    on_error=lambda exc: _handle_async_error(exc),
                )
        except Exception as exc:
            log_error(f"Event handler for '{event_type}' raised: {exc}", exc)
        if evt._stopped:
            break
    # One native dispatch is one reactive batch, even when ancestors also write.
    _core.flush()
    return (kernel.FLAG_STOP_PROPAGATION if evt._stopped else 0) | (
        kernel.FLAG_PREVENT_DEFAULT if evt._default_prevented else 0
    )


def _handle_async_error(exc: BaseException) -> None:
    import asyncio

    if not isinstance(exc, asyncio.CancelledError):
        log_error(f"Async event handler raised: {exc}", exc)


kernel.set_event_dispatcher(dispatch_event)
