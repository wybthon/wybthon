"""Tests for the ``Element`` wrapper's convenience properties.

These mirror common JS DOM properties (``value``, ``checked``, ``files``)
so handlers can write ``evt.target.value`` exactly as in JS/React/Solid
without reaching into ``evt.target.element``.
"""

from types import SimpleNamespace

from conftest import StubNode

import wybthon  # noqa: F401  (force initial import before stub-aware reloads)


def test_element_value_property_reads_from_underlying_node(wyb):
    dom = wyb["dom"]

    node = StubNode(tag="input")
    node.value = "hello"
    el = dom.Element(node=node)

    assert el.value == "hello"


def test_element_value_property_writes_to_underlying_node(wyb):
    dom = wyb["dom"]

    node = StubNode(tag="input")
    el = dom.Element(node=node)

    el.value = "world"
    assert node.value == "world"


def test_element_checked_property_reads_and_writes(wyb):
    dom = wyb["dom"]

    node = StubNode(tag="input")
    node.checked = True
    el = dom.Element(node=node)

    assert el.checked is True
    el.checked = False
    assert node.checked is False


def test_element_files_property_proxies_underlying(wyb):
    dom = wyb["dom"]

    fake_files = ["a.txt", "b.txt"]
    node = StubNode(tag="input")
    node.files = fake_files
    el = dom.Element(node=node)

    assert el.files == fake_files


def test_element_value_returns_none_when_node_lacks_value(wyb):
    """A node without a ``value`` attr (e.g. plain div) should return None."""
    dom = wyb["dom"]

    raw = SimpleNamespace()  # bare object, no attributes at all
    el = dom.Element(node=raw)

    assert el.value is None
    assert el.checked is False
    assert el.files is None


def test_dom_event_target_value_matches_js_pattern(wyb):
    """``evt.target.value`` should "just work" inside an event handler."""
    events = wyb["events"]

    captured = []
    target_node = StubNode(tag="input")
    target_node.value = "typed text"
    target_node.checked = True

    js_evt = SimpleNamespace(
        type="input",
        target=target_node,
        preventDefault=lambda: None,
        stopPropagation=lambda: None,
    )

    evt = events.DomEvent(js_evt)
    captured.append(evt.target.value)
    captured.append(evt.target.checked)

    assert captured == ["typed text", True]
