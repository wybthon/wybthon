"""E2E: transitions hold the UI together, actions reveal optimistic values."""

import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e


def test_header_and_body_update_together(goto_feature):
    page = goto_feature("transitions")
    expect(page.get_by_test_id("tx-head")).to_have_text("id=1")
    expect(page.get_by_test_id("tx-body")).to_have_text("user1")
    expect(page.get_by_test_id("tx-state")).to_have_text("idle")

    page.get_by_test_id("tx-select").click()
    # The header is held with the pending body; only the indicator moves.
    expect(page.get_by_test_id("tx-state")).to_have_text("pending")
    expect(page.get_by_test_id("tx-head")).to_have_text("id=1")
    expect(page.get_by_test_id("tx-body")).to_have_text("user1")

    page.get_by_test_id("tx-resolve").click()
    expect(page.get_by_test_id("tx-head")).to_have_text("id=2")
    expect(page.get_by_test_id("tx-body")).to_have_text("user2")
    expect(page.get_by_test_id("tx-state")).to_have_text("idle")


def test_action_shows_optimistic_value_then_real_one(goto_feature):
    page = goto_feature("transitions")
    expect(page.get_by_test_id("tx-saved")).to_have_text("none")
    expect(page.get_by_test_id("tx-saving")).to_have_text("no")

    page.get_by_test_id("tx-save").click()
    expect(page.get_by_test_id("tx-saved")).to_have_text("done (saving)")
    expect(page.get_by_test_id("tx-saving")).to_have_text("yes")

    page.get_by_test_id("tx-finish").click()
    expect(page.get_by_test_id("tx-saved")).to_have_text("done")
    expect(page.get_by_test_id("tx-saving")).to_have_text("no")


def test_reveal_is_sequential(goto_feature):
    page = goto_feature("transitions")
    expect(page.get_by_test_id("tx-fa")).to_have_text("fa")
    expect(page.get_by_test_id("tx-fb")).to_have_text("fb")

    # B resolving first stays in its fallback until A is ready.
    page.get_by_test_id("tx-resolve-b").click()
    expect(page.get_by_test_id("tx-fa")).to_have_text("fa")
    expect(page.get_by_test_id("tx-fb")).to_have_text("fb")
    expect(page.get_by_test_id("tx-b")).to_have_count(0)

    page.get_by_test_id("tx-resolve-a").click()
    expect(page.get_by_test_id("tx-a")).to_have_text("A")
    expect(page.get_by_test_id("tx-b")).to_have_text("B")
