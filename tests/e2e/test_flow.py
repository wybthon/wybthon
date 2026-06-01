"""E2E: flow control (Show, For, Index, Switch/Match, Dynamic)."""

import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e


def test_show_toggles_branches(goto_feature):
    page = goto_feature("flow")
    expect(page.get_by_test_id("flow-show-on")).to_have_text("shown")
    expect(page.get_by_test_id("flow-show-off")).to_have_count(0)

    page.get_by_test_id("flow-show-toggle").click()
    expect(page.get_by_test_id("flow-show-off")).to_have_text("hidden")
    expect(page.get_by_test_id("flow-show-on")).to_have_count(0)


def test_for_keyed_add_remove_reorder(goto_feature):
    page = goto_feature("flow")
    items = page.get_by_test_id("flow-for-list").locator("li")
    expect(page.get_by_test_id("flow-for-count")).to_have_text("3")
    expect(items).to_have_text(["0:alpha", "1:beta", "2:gamma"])

    page.get_by_test_id("flow-for-add").click()
    expect(page.get_by_test_id("flow-for-count")).to_have_text("4")
    expect(items).to_have_text(["0:alpha", "1:beta", "2:gamma", "3:item-1"])

    page.get_by_test_id("flow-for-remove").click()
    expect(page.get_by_test_id("flow-for-count")).to_have_text("3")

    page.get_by_test_id("flow-for-reverse").click()
    expect(items).to_have_text(["0:gamma", "1:beta", "2:alpha"])


def test_index_list_reuses_slots(goto_feature):
    page = goto_feature("flow")
    items = page.get_by_test_id("flow-index-list").locator("li")
    expect(items).to_have_text(["[0]alpha", "[1]beta", "[2]gamma"])
    page.get_by_test_id("flow-for-reverse").click()
    expect(items).to_have_text(["[0]gamma", "[1]beta", "[2]alpha"])


def test_switch_match(goto_feature):
    page = goto_feature("flow")
    expect(page.get_by_test_id("flow-switch-out")).to_have_text("idle")
    page.get_by_test_id("flow-switch-cycle").click()
    expect(page.get_by_test_id("flow-switch-out")).to_have_text("loading")
    page.get_by_test_id("flow-switch-cycle").click()
    expect(page.get_by_test_id("flow-switch-out")).to_have_text("ready")
    page.get_by_test_id("flow-switch-cycle").click()
    expect(page.get_by_test_id("flow-switch-out")).to_have_text("idle")


def test_dynamic_component_tag(goto_feature):
    page = goto_feature("flow")
    out = page.get_by_test_id("flow-dyn-out")
    expect(out).to_have_text("dyn")
    assert out.evaluate("el => el.tagName") == "H3"
    page.get_by_test_id("flow-dyn-cycle").click()
    assert page.get_by_test_id("flow-dyn-out").evaluate("el => el.tagName") == "H2"
    page.get_by_test_id("flow-dyn-cycle").click()
    assert page.get_by_test_id("flow-dyn-out").evaluate("el => el.tagName") == "P"
