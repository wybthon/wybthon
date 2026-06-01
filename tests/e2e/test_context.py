"""E2E: context provider propagation, nested override, and default fallback."""

import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e


def test_context_values_and_reactive_update(goto_feature):
    page = goto_feature("context")
    expect(page.get_by_test_id("ctx-outer")).to_have_text("light")
    expect(page.get_by_test_id("ctx-inner")).to_have_text("override")
    expect(page.get_by_test_id("ctx-default")).to_have_text("default-theme")

    page.get_by_test_id("ctx-toggle").click()
    # Outer consumer tracks the provider's signal; nested override and the
    # provider-less default are unaffected.
    expect(page.get_by_test_id("ctx-outer")).to_have_text("dark")
    expect(page.get_by_test_id("ctx-inner")).to_have_text("override")
    expect(page.get_by_test_id("ctx-default")).to_have_text("default-theme")
