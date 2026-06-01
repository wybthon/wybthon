"""E2E: ErrorBoundary catches a child render error, then recovers via reset_key."""

import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e


def test_error_boundary_catches(goto_feature):
    page = goto_feature("errors")
    expect(page.get_by_test_id("err-fallback")).to_contain_text("caught: boom")
    expect(page.get_by_test_id("err-ok")).to_have_count(0)


def test_error_boundary_resets(goto_feature):
    page = goto_feature("errors")
    page.get_by_test_id("err-fix").click()
    # Fixing the child and bumping reset_key clears the boundary.
    expect(page.get_by_test_id("err-ok")).to_have_text("recovered")
    expect(page.get_by_test_id("err-fallback")).to_have_count(0)
