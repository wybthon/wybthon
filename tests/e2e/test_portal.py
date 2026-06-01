"""E2E: Portal renders children into a different container while staying reactive."""

import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e


def test_portal_targets_other_container(goto_feature):
    page = goto_feature("portal")
    expect(page.get_by_test_id("portal-content")).to_have_count(0)

    page.get_by_test_id("portal-toggle").click()
    # Content is mounted inside the target container, not its source site.
    expect(page.locator("[data-testid=portal-target] [data-testid=portal-content]")).to_have_count(1)
    expect(page.locator("[data-testid=portal-source] [data-testid=portal-content]")).to_have_count(0)


def test_portal_content_stays_reactive(goto_feature):
    page = goto_feature("portal")
    page.get_by_test_id("portal-toggle").click()
    expect(page.get_by_test_id("portal-count")).to_have_text("0")
    page.get_by_test_id("portal-inc").click()
    expect(page.get_by_test_id("portal-count")).to_have_text("1")


def test_portal_unmounts(goto_feature):
    page = goto_feature("portal")
    page.get_by_test_id("portal-toggle").click()
    expect(page.get_by_test_id("portal-content")).to_have_count(1)
    page.get_by_test_id("portal-toggle").click()
    expect(page.get_by_test_id("portal-content")).to_have_count(0)
