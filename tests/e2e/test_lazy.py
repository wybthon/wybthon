"""E2E: lazy component loading (resolved target and missing-module error)."""

import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e


def test_lazy_component_loads(goto_feature):
    page = goto_feature("lazy")
    expect(page.get_by_test_id("lazy-loaded")).to_have_text("lazy-loaded")


def test_lazy_missing_module_shows_error(goto_path):
    page = goto_path("/lazy-error", wait_selector=".lazy-error")
    # load_component on a missing module renders the loader's error fallback.
    expect(page.locator(".lazy-error")).to_contain_text("Failed to load")
