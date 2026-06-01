"""E2E: Suspense shows a fallback while a resource loads, then children."""

import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e


def test_fallback_then_content(goto_feature):
    page = goto_feature("suspense")
    expect(page.get_by_test_id("susp-fallback")).to_have_text("loading")
    expect(page.get_by_test_id("susp-content")).to_have_count(0)

    page.get_by_test_id("susp-resolve").click()
    expect(page.get_by_test_id("susp-content")).to_have_text("payload-1")
    expect(page.get_by_test_id("susp-fallback")).to_have_count(0)


def test_reload_shows_fallback_again(goto_feature):
    page = goto_feature("suspense")
    page.get_by_test_id("susp-resolve").click()
    expect(page.get_by_test_id("susp-content")).to_have_text("payload-1")

    page.get_by_test_id("susp-reload").click()
    expect(page.get_by_test_id("susp-fallback")).to_have_text("loading")

    page.get_by_test_id("susp-resolve").click()
    expect(page.get_by_test_id("susp-content")).to_have_text("payload-2")
