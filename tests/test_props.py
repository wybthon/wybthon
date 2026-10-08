"""Tests for the private DOM prop module (prop-name utilities).

The DOM-dependent parts of `wybthon._dom_props` are tested via the VDOM
integration tests. These tests exercise its pure string utilities.
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
    props = importlib.import_module("wybthon._dom_props")
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


def test_attr_name_maps_pythonic_names(browser_stubs):
    props = _load_props()
    assert props.attr_name("class_") == "class"
    assert props.attr_name("html_for") == "for"
    assert props.attr_name("for_") == "for"
    assert props.attr_name("aria_label") == "aria-label"
    assert props.attr_name("data_testid") == "data-testid"
    assert props.attr_name("title") == "title"


def test_html_helpers_keep_pythonic_names_in_vnode_props(browser_stubs):
    from wybthon.html import div, label

    assert div(class_="x").props == {"class_": "x"}
    assert label(html_for="name").props == {"html_for": "name"}
