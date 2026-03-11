"""Tests for the props module (prop-name utilities).

The DOM-dependent parts of props.py are tested via the VDOM integration tests.
These tests exercise the pure string-utility functions that were re-exported
via vdom.py's ``is_event_prop`` alias.
"""

import importlib
import sys
from types import ModuleType


class _Document:
    def __init__(self):
        self._listeners = {}

    def createElement(self, tag):
        return None

    def createTextNode(self, text):
        return None

    def addEventListener(self, event_type, proxy):
        pass

    def removeEventListener(self, event_type, proxy):
        pass

    def querySelector(self, sel):
        return None


def _install_stubs():
    saved = {name: sys.modules.get(name) for name in ("js", "pyodide", "pyodide.ffi")}
    js_mod = ModuleType("js")
    js_mod.document = _Document()
    js_mod.fetch = lambda url: None
    sys.modules["js"] = js_mod
    pyodide = ModuleType("pyodide")
    ffi = ModuleType("pyodide.ffi")
    ffi.create_proxy = lambda fn: fn
    sys.modules["pyodide"] = pyodide
    sys.modules["pyodide.ffi"] = ffi
    setattr(pyodide, "ffi", ffi)
    return saved


def _restore(saved):
    for name, mod in saved.items():
        if mod is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = mod


def _load_props():
    dom = importlib.import_module("wybthon.dom")
    importlib.reload(dom)
    events = importlib.import_module("wybthon.events")
    importlib.reload(events)
    warnings_mod = importlib.import_module("wybthon._warnings")
    importlib.reload(warnings_mod)
    props = importlib.import_module("wybthon.props")
    importlib.reload(props)
    return props


def test_is_event_prop_underscore():
    saved = _install_stubs()
    try:
        props = _load_props()
        assert props.is_event_prop("on_click") is True
        assert props.is_event_prop("on_input") is True
        assert props.is_event_prop("on_change") is True
    finally:
        _restore(saved)


def test_is_event_prop_camel():
    saved = _install_stubs()
    try:
        props = _load_props()
        assert props.is_event_prop("onClick") is True
        assert props.is_event_prop("onInput") is True
    finally:
        _restore(saved)


def test_is_event_prop_non_event():
    saved = _install_stubs()
    try:
        props = _load_props()
        assert props.is_event_prop("class") is False
        assert props.is_event_prop("style") is False
        assert props.is_event_prop("on") is False
        assert props.is_event_prop("one") is False
    finally:
        _restore(saved)


def test_event_name_from_prop_underscore():
    saved = _install_stubs()
    try:
        props = _load_props()
        assert props.event_name_from_prop("on_click") == "click"
        assert props.event_name_from_prop("on_input") == "input"
    finally:
        _restore(saved)


def test_event_name_from_prop_camel():
    saved = _install_stubs()
    try:
        props = _load_props()
        assert props.event_name_from_prop("onClick") == "click"
        assert props.event_name_from_prop("onInput") == "input"
    finally:
        _restore(saved)


def test_event_name_from_prop_passthrough():
    saved = _install_stubs()
    try:
        props = _load_props()
        assert props.event_name_from_prop("click") == "click"
    finally:
        _restore(saved)


def test_to_kebab():
    saved = _install_stubs()
    try:
        props = _load_props()
        assert props.to_kebab("backgroundColor") == "background-color"
        assert props.to_kebab("fontSize") == "font-size"
        assert props.to_kebab("color") == "color"
        assert props.to_kebab("borderTopWidth") == "border-top-width"
    finally:
        _restore(saved)
