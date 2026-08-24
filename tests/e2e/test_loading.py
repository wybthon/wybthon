"""E2E: Loading shows a fallback while an async memo loads, then children."""

import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e


def test_fallback_then_content(goto_feature):
    page = goto_feature("loading")
    expect(page.get_by_test_id("load-fallback")).to_have_text("loading")
    expect(page.get_by_test_id("load-content")).to_have_count(0)

    page.get_by_test_id("load-resolve").click()
    expect(page.get_by_test_id("load-content")).to_have_text("payload-1")
    expect(page.get_by_test_id("load-fallback")).to_have_count(0)


def test_reload_keeps_content_until_new_data(goto_feature):
    """Revalidations don't re-trigger the boundary; stale data stays visible."""
    page = goto_feature("loading")
    page.get_by_test_id("load-resolve").click()
    expect(page.get_by_test_id("load-content")).to_have_text("payload-1")

    page.get_by_test_id("load-reload").click()
    expect(page.get_by_test_id("load-content")).to_have_text("payload-1")
    expect(page.get_by_test_id("load-fallback")).to_have_count(0)

    page.get_by_test_id("load-resolve").click()
    expect(page.get_by_test_id("load-content")).to_have_text("payload-2")
