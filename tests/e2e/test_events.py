"""E2E: event delegation, bubbling, stopPropagation, and target reads."""

import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e


def test_stop_propagation_blocks_bubbling(goto_feature):
    page = goto_feature("events")
    expect(page.get_by_test_id("ev-outer-count")).to_have_text("0")
    expect(page.get_by_test_id("ev-inner-count")).to_have_text("0")

    page.get_by_test_id("ev-inner-stop").click()
    expect(page.get_by_test_id("ev-inner-count")).to_have_text("1")
    expect(page.get_by_test_id("ev-outer-count")).to_have_text("0")


def test_bubbling_reaches_delegated_ancestor(goto_feature):
    page = goto_feature("events")
    page.get_by_test_id("ev-inner-bubble").click()
    expect(page.get_by_test_id("ev-inner-count")).to_have_text("1")
    expect(page.get_by_test_id("ev-outer-count")).to_have_text("1")


def test_target_value_and_checked(goto_feature):
    page = goto_feature("events")
    page.get_by_test_id("ev-input").fill("hi there")
    expect(page.get_by_test_id("ev-input-echo")).to_have_text("hi there")

    expect(page.get_by_test_id("ev-check-echo")).to_have_text("off")
    page.get_by_test_id("ev-check").check()
    expect(page.get_by_test_id("ev-check-echo")).to_have_text("on")
