"""Tests for the props module (prop-name utilities).

The DOM-dependent parts of props.py are tested via the VDOM integration tests.
These tests exercise the pure string-utility functions that were re-exported
via vdom.py's ``is_event_prop`` alias.
"""

import importlib

import wybthon  # noqa: F401


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


def test_is_event_prop_underscore(browser_stubs):
    props = _load_props()
    assert props.is_event_prop("on_click") is True
    assert props.is_event_prop("on_input") is True
    assert props.is_event_prop("on_change") is True


def test_is_event_prop_camel(browser_stubs):
    props = _load_props()
    assert props.is_event_prop("onClick") is True
    assert props.is_event_prop("onInput") is True


def test_is_event_prop_non_event(browser_stubs):
    props = _load_props()
    assert props.is_event_prop("class") is False
    assert props.is_event_prop("style") is False
    assert props.is_event_prop("on") is False
    assert props.is_event_prop("one") is False


def test_event_name_from_prop_underscore(browser_stubs):
    props = _load_props()
    assert props.event_name_from_prop("on_click") == "click"
    assert props.event_name_from_prop("on_input") == "input"


def test_event_name_from_prop_camel(browser_stubs):
    props = _load_props()
    assert props.event_name_from_prop("onClick") == "click"
    assert props.event_name_from_prop("onInput") == "input"


def test_event_name_from_prop_passthrough(browser_stubs):
    props = _load_props()
    assert props.event_name_from_prop("click") == "click"


def test_to_kebab(browser_stubs):
    props = _load_props()
    assert props.to_kebab("backgroundColor") == "background-color"
    assert props.to_kebab("fontSize") == "font-size"
    assert props.to_kebab("color") == "color"
    assert props.to_kebab("borderTopWidth") == "border-top-width"
