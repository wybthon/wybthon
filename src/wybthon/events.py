"""Event delegation utilities for VDOM event handling in the browser.

Wybthon installs **one** root listener per event type on `document`
and dispatches to per-node handlers using a stable `data-wybid`
attribute. This keeps the number of native listeners small even for
large trees and lets the renderer add or remove handlers cheaply
during reconciliation.

Public surface:

- [`DomEvent`][wybthon.DomEvent]: a thin wrapper passed to handlers
  exposing `type`, `target`, `current_target`, and helpers like
  [`prevent_default`][wybthon.DomEvent.prevent_default] and
  [`stop_propagation`][wybthon.DomEvent.stop_propagation].

The remaining helpers are internal: [`set_handler`][wybthon.events.set_handler],
[`remove_all_for`][wybthon.events.remove_all_for], and the listener
ref-counting utilities are exercised by the renderer.

See Also:
    - [Forms guide](../concepts/forms.md)
"""

from typing import Any, Callable, Dict, Optional

try:
    from .dom import Element
except Exception:  # pragma: no cover - exercised in non-browser tests

    class Element:  # type: ignore
        """Minimal `Element` stub used in non-browser/test environments."""

        def __init__(self, tag: Optional[str] = None, existing: bool = False, node=None) -> None:
            """Wrap an opaque DOM-like `node` reference for tests."""
            self.element = node


__all__ = ["DomEvent"]


_NODE_ID_ATTR = "data-wybid"
_next_id = 0
_handlers: Dict[str, Dict[str, Callable]] = {}
_listeners: Dict[str, object] = {}
_event_counts: Dict[str, int] = {}


def _get_or_assign_id(node) -> str:
    """Return a stable id for a DOM node, assigning one if missing.

    The id is stored on the node as a `data-wybid` attribute so that
    the delegated dispatcher can map a click target back to the
    Wybthon-side handler table.

    Args:
        node: Underlying DOM node to identify.

    Returns:
        The existing or newly-assigned id as a string.
    """
    wid = None
    try:
        wid = node.getAttribute(_NODE_ID_ATTR)
    except Exception:
        wid = None
    if wid:
        return wid
    global _next_id
    _next_id += 1
    wid = str(_next_id)
    try:
        node.setAttribute(_NODE_ID_ATTR, wid)
    except Exception:
        pass
    return wid


def _event_prop_to_type(name: str) -> str:
    """Normalize a prop name like `on_click` or `onClick` to a plain event type.

    Args:
        name: Prop key as seen on a `VNode` (e.g. `"on_click"`).

    Returns:
        The lower-cased event type (e.g. `"click"`).
    """
    if name.startswith("on_"):
        return name[3:]
    if name.startswith("on"):
        return name[2:].lower()
    return name


class DomEvent:
    """Thin wrapper around a JS event with convenience helpers.

    Attributes:
        type: Event type string (e.g. `"click"`).
        target: The original event target as an
            [`Element`][wybthon.Element], or `None` if unavailable.
        current_target: The currently-dispatched element while
            bubbling through delegated handlers; updated by the
            dispatcher.
    """

    def __init__(self, js_event: Any) -> None:
        """Wrap a raw JS event object.

        Args:
            js_event: The native browser event object.
        """
        self._js_event = js_event
        self.type = getattr(js_event, "type", None)
        tgt = getattr(js_event, "target", None)
        self.target = Element(node=tgt) if tgt is not None else None
        self.current_target: Optional[Element] = None
        self._stopped = False

    def prevent_default(self) -> None:
        """Prevent the default browser action for this event, if possible."""
        try:
            self._js_event.preventDefault()
        except Exception:
            pass

    def stop_propagation(self) -> None:
        """Stop propagation through both the JS and the delegated chains.

        Sets an internal flag that causes Wybthon's dispatcher to stop
        walking the DOM ancestors, and also calls the native
        `stopPropagation` so other JS listeners do not fire.
        """
        self._stopped = True
        try:
            self._js_event.stopPropagation()
        except Exception:
            pass


def _ensure_root_listener(event_type: str) -> None:
    """Install a single delegated root listener for `event_type`, idempotently."""
    if event_type in _listeners:
        return
    from js import document
    from pyodide.ffi import create_proxy

    def dispatcher(js_event) -> None:
        """Walk from `target` up the tree and invoke registered handlers."""
        try:
            node = getattr(js_event, "target", None)
            evt = DomEvent(js_event)
            while node is not None:
                try:
                    wid = node.getAttribute(_NODE_ID_ATTR)
                except Exception:
                    wid = None
                if wid is not None:
                    mapping = _handlers.get(wid)
                    if mapping is not None:
                        handler = mapping.get(event_type)
                        if handler is not None:
                            evt.current_target = Element(node=node)
                            handler(evt)
                            if evt._stopped:
                                break
                node = getattr(node, "parentNode", None)
        except Exception as e:
            try:
                print("Event dispatch error:", e)
            except Exception:
                pass

    proxy = create_proxy(dispatcher)
    document.addEventListener(event_type, proxy)
    _listeners[event_type] = proxy


def _teardown_root_listener(event_type: str) -> None:
    """Remove the delegated root listener for `event_type` if installed.

    Best-effort: safe to call repeatedly and from non-browser contexts.
    Errors are swallowed so teardown never raises.
    """
    try:
        if event_type in _listeners:
            try:
                from js import document
            except Exception:
                document = None
            proxy = _listeners.pop(event_type, None)
            if document is not None and proxy is not None:
                try:
                    document.removeEventListener(event_type, proxy)
                except Exception:
                    pass
    except Exception:
        pass


def _increment_event_count(event_type: str) -> None:
    """Increment the global active-handler count for `event_type`."""
    _event_counts[event_type] = _event_counts.get(event_type, 0) + 1


def _decrement_event_count(event_type: str) -> None:
    """Decrement the active-handler count and tear down listeners at zero."""
    current = _event_counts.get(event_type, 0)
    if current <= 1:
        if event_type in _event_counts:
            del _event_counts[event_type]
        _teardown_root_listener(event_type)
    else:
        _event_counts[event_type] = current - 1


def set_handler(el: Element, event_prop_name: str, handler: Optional[Callable]) -> None:
    """Attach, update, or remove a handler for an event property on an element.

    Args:
        el: Wrapped element to attach to.
        event_prop_name: Prop name as seen on the `VNode` (e.g.
            `"on_click"`); normalized to the underlying DOM event type
            (`"on_click"` → `"click"`).
        handler: Callback to invoke. Pass `None` to remove an existing
            handler for this event type on this element.
    """
    event_type = _event_prop_to_type(event_prop_name)
    wid = _get_or_assign_id(el.element)
    mapping = _handlers.get(wid)
    if mapping is None:
        mapping = {}
        _handlers[wid] = mapping

    had_previous = event_type in mapping

    if handler is None:
        if had_previous:
            del mapping[event_type]
            _decrement_event_count(event_type)
            if not mapping:
                _handlers.pop(wid, None)
        return

    if not had_previous:
        _increment_event_count(event_type)
        _ensure_root_listener(event_type)
    mapping[event_type] = handler


def remove_all_for(el: Element) -> None:
    """Remove every delegated handler registered for `el`.

    Called by the renderer during unmount to drop the handler table
    and decrement the active-listener counters so unused root
    listeners are released.
    """
    try:
        wid = el.element.getAttribute(_NODE_ID_ATTR)
    except Exception:
        wid = None
    if wid is not None:
        mapping = _handlers.pop(wid, None)
        if isinstance(mapping, dict):
            for evt_type in list(mapping.keys()):
                _decrement_event_count(evt_type)
