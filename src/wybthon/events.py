"""Event delegation utilities for VDOM event handling in the browser."""

from typing import Callable, Dict, Optional

# Allow importing this module outside the browser (no js/pyodide) by
# providing a minimal Element stub if importing from wybthon.dom fails.
try:
    from .dom import Element
except Exception:  # pragma: no cover - exercised in non-browser tests

    class Element:  # type: ignore
        """Minimal Element stub used in non-browser/test environments."""

        def __init__(self, tag: Optional[str] = None, existing: bool = False, node=None) -> None:
            self.element = node


__all__ = ["DomEvent"]


_NODE_ID_ATTR = "data-wybid"
_next_id = 0
_handlers: Dict[str, Dict[str, Callable]] = {}
_listeners: Dict[str, object] = {}
# Track number of active handlers per event type across all nodes
_event_counts: Dict[str, int] = {}


def _get_or_assign_id(node) -> str:
    """Return a stable id for a DOM node, assigning one if missing."""
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
    """Normalize prop names like on_click/onClick to a plain event type."""
    if name.startswith("on_"):
        return name[3:]
    if name.startswith("on"):
        return name[2:].lower()
    return name


class DomEvent:
    """Thin wrapper around a JS event with convenience helpers."""

    def __init__(self, js_event) -> None:
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
        """Stop propagation through the delegated listener chain."""
        self._stopped = True
        try:
            self._js_event.stopPropagation()
        except Exception:
            pass


def _ensure_root_listener(event_type: str) -> None:
    """Install a single delegated root listener for the given event type."""
    if event_type in _listeners:
        return
    from js import document
    from pyodide.ffi import create_proxy

    def dispatcher(js_event) -> None:
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
            # Surface in console but don't crash
            try:
                print("Event dispatch error:", e)
            except Exception:
                pass

    proxy = create_proxy(dispatcher)
    document.addEventListener(event_type, proxy)
    _listeners[event_type] = proxy


def _teardown_root_listener(event_type: str) -> None:
    """Remove the delegated root listener if it is currently installed."""
    # Best-effort removal; safe in non-browser contexts
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
        # Never raise from teardown
        pass


def _increment_event_count(event_type: str) -> None:
    """Increment global active-handler count for an event type."""
    _event_counts[event_type] = _event_counts.get(event_type, 0) + 1


def _decrement_event_count(event_type: str) -> None:
    """Decrement count and teardown root listener when the last handler is removed."""
    current = _event_counts.get(event_type, 0)
    if current <= 1:
        if event_type in _event_counts:
            del _event_counts[event_type]
        _teardown_root_listener(event_type)
    else:
        _event_counts[event_type] = current - 1


def set_handler(el: Element, event_prop_name: str, handler: Optional[Callable]) -> None:
    """Attach/update/remove a handler for a given event property on an element."""
    event_type = _event_prop_to_type(event_prop_name)
    wid = _get_or_assign_id(el.element)
    mapping = _handlers.get(wid)
    if mapping is None:
        mapping = {}
        _handlers[wid] = mapping

    had_previous = event_type in mapping

    # Removing handler
    if handler is None:
        if had_previous:
            del mapping[event_type]
            _decrement_event_count(event_type)
            # Optional: prune empty per-node mapping
            if not mapping:
                _handlers.pop(wid, None)
        return

    # Adding or updating handler
    if not had_previous:
        # First handler for this event type on this node
        _increment_event_count(event_type)
        _ensure_root_listener(event_type)
    mapping[event_type] = handler


def remove_all_for(el: Element) -> None:
    """Remove all delegated handlers associated with the element's id."""
    try:
        wid = el.element.getAttribute(_NODE_ID_ATTR)
    except Exception:
        wid = None
    if wid is not None:
        mapping = _handlers.pop(wid, None)
        if isinstance(mapping, dict):
            # Decrement counts for all event types previously registered on this node
            for evt_type in list(mapping.keys()):
                _decrement_event_count(evt_type)
