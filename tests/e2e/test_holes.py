"""E2E: reactive holes (text, derived expression, node, independence)."""

import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e


def test_text_hole(goto_feature):
    page = goto_feature("holes")
    expect(page.get_by_test_id("hole-text")).to_have_text("0")
    page.get_by_test_id("hole-text-inc").click()
    page.get_by_test_id("hole-text-inc").click()
    expect(page.get_by_test_id("hole-text")).to_have_text("2")


def test_derived_expression_hole(goto_feature):
    page = goto_feature("holes")
    expect(page.get_by_test_id("hole-greeting")).to_have_text("Hello, Ada Lovelace!")
    page.get_by_test_id("hole-first").fill("Grace")
    expect(page.get_by_test_id("hole-greeting")).to_have_text("Hello, Grace Lovelace!")
    page.get_by_test_id("hole-last").fill("Hopper")
    expect(page.get_by_test_id("hole-greeting")).to_have_text("Hello, Grace Hopper!")


def test_node_hole(goto_feature):
    page = goto_feature("holes")
    expect(page.get_by_test_id("hole-node-inner")).to_have_text("alpha")
    page.get_by_test_id("hole-node-cycle").click()
    expect(page.get_by_test_id("hole-node-inner")).to_have_text("bravo")
    page.get_by_test_id("hole-node-cycle").click()
    expect(page.get_by_test_id("hole-node-inner")).to_have_text("charlie")


def test_independent_holes(goto_feature):
    page = goto_feature("holes")
    expect(page.get_by_test_id("hole-x-runs")).to_have_text("1")
    expect(page.get_by_test_id("hole-y-runs")).to_have_text("1")

    page.get_by_test_id("hole-x-inc").click()
    expect(page.get_by_test_id("hole-x")).to_have_text("1")
    expect(page.get_by_test_id("hole-x-runs")).to_have_text("2")
    # The y hole did not re-evaluate when only x changed.
    expect(page.get_by_test_id("hole-y-runs")).to_have_text("1")
