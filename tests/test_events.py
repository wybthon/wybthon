import importlib
import sys
from types import ModuleType, SimpleNamespace

from conftest import restore_modules


def make_dummy_js_event(**kwargs):
    target = kwargs.pop("target", SimpleNamespace(getAttribute=lambda n: None))
    defaults = {
        "type": "click",
        "target": target,
        "preventDefault": lambda: None,
        "stopPropagation": lambda: None,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_domevent_shape_and_methods_imports_without_browser():
    from wybthon.events import DomEvent

    js_evt = make_dummy_js_event()
    evt = DomEvent(js_evt)

    assert evt.type == "click"
    assert evt.target is not None
    evt.prevent_default()
    evt.stop_propagation()


def test_event_prop_normalization():
    from wybthon.events import _event_prop_to_type

    assert _event_prop_to_type("on_click") == "click"
    assert _event_prop_to_type("onClick") == "click"
    assert _event_prop_to_type("onclick") == "click"
    assert _event_prop_to_type("on_input") == "input"
    assert _event_prop_to_type("onInput") == "input"


class _TrackingDocument:
    """Stub document that tracks addEventListener/removeEventListener calls."""

    def __init__(self):
        self.listeners = {}
        self.add_calls = {}
        self.remove_calls = {}

    def addEventListener(self, event_type, proxy):
        self.listeners.setdefault(event_type, set()).add(proxy)
        self.add_calls[event_type] = self.add_calls.get(event_type, 0) + 1

    def removeEventListener(self, event_type, proxy):
        s = self.listeners.get(event_type)
        if s is not None and proxy in s:
            s.remove(proxy)
        self.remove_calls[event_type] = self.remove_calls.get(event_type, 0) + 1

    def createElement(self, tag):
        return SimpleNamespace()

    def querySelector(self, sel):
        return SimpleNamespace()


def _install_tracking_stubs():
    """Install stubs with a tracking document for event delegation tests."""
    saved = {name: sys.modules.get(name) for name in ("js", "pyodide", "pyodide.ffi")}

    js_mod = ModuleType("js")
    doc = _TrackingDocument()
    js_mod.document = doc
    js_mod.fetch = lambda url: None
    sys.modules["js"] = js_mod

    pyodide_mod = ModuleType("pyodide")
    ffi_mod = ModuleType("pyodide.ffi")
    ffi_mod.create_proxy = lambda fn: fn
    sys.modules["pyodide"] = pyodide_mod
    sys.modules["pyodide.ffi"] = ffi_mod
    setattr(pyodide_mod, "ffi", ffi_mod)

    return saved, doc


def _make_dummy_node():
    attrs = {}

    def getAttribute(name):
        return attrs.get(name)

    def setAttribute(name, value):
        attrs[name] = value

    return SimpleNamespace(getAttribute=getAttribute, setAttribute=setAttribute, parentNode=None)


def test_delegated_listener_teardown_on_unset_handler():
    saved, doc = _install_tracking_stubs()
    try:
        dom_mod = importlib.import_module("wybthon.dom")
        importlib.reload(dom_mod)
        events_mod = importlib.import_module("wybthon.events")
        importlib.reload(events_mod)

        el = dom_mod.Element(node=_make_dummy_node())

        assert "click" not in events_mod._listeners

        def handler1(_e):
            return None

        events_mod.set_handler(el, "on_click", handler1)
        assert events_mod._event_counts.get("click", 0) == 1
        assert doc.add_calls.get("click", 0) == 1
        assert "click" in events_mod._listeners

        def handler2(_e):
            return None

        events_mod.set_handler(el, "on_click", handler2)
        assert events_mod._event_counts.get("click", 0) == 1
        assert doc.add_calls.get("click", 0) == 1

        events_mod.set_handler(el, "on_click", None)
        assert events_mod._event_counts.get("click") is None
        assert doc.remove_calls.get("click", 0) == 1
        assert "click" not in events_mod._listeners
    finally:
        restore_modules(saved)


def test_remove_all_for_prunes_all_event_types_and_tears_down_root_listeners():
    saved, doc = _install_tracking_stubs()
    try:
        dom_mod = importlib.import_module("wybthon.dom")
        importlib.reload(dom_mod)
        events_mod = importlib.import_module("wybthon.events")
        importlib.reload(events_mod)

        el = dom_mod.Element(node=_make_dummy_node())

        events_mod.set_handler(el, "on_click", lambda e: None)
        events_mod.set_handler(el, "on_input", lambda e: None)
        assert events_mod._event_counts.get("click", 0) == 1
        assert events_mod._event_counts.get("input", 0) == 1
        assert doc.add_calls.get("click", 0) == 1
        assert doc.add_calls.get("input", 0) == 1

        events_mod.remove_all_for(el)
        assert events_mod._event_counts.get("click") is None
        assert events_mod._event_counts.get("input") is None
        assert doc.remove_calls.get("click", 0) == 1
        assert doc.remove_calls.get("input", 0) == 1
        assert "click" not in events_mod._listeners
        assert "input" not in events_mod._listeners
    finally:
        restore_modules(saved)
