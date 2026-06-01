"""E2E: form state, two-way bindings, live validation, and validated submit."""

import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e


def test_live_validation(goto_feature):
    page = goto_feature("forms")
    expect(page.get_by_test_id("form-result")).to_have_text("")

    page.get_by_test_id("form-name").fill("A")
    expect(page.get_by_test_id("form-name-err")).to_have_text("Minimum length is 2")

    page.get_by_test_id("form-name").fill("")
    expect(page.get_by_test_id("form-name-err")).to_have_text("This field is required")

    page.get_by_test_id("form-name").fill("Ada")
    expect(page.get_by_test_id("form-name-err")).to_have_text("")

    page.get_by_test_id("form-email").fill("bad")
    expect(page.get_by_test_id("form-email-err")).to_have_text("Invalid email address")


def test_aria_invalid_attribute(goto_feature):
    page = goto_feature("forms")
    expect(page.get_by_test_id("form-name")).to_have_attribute("aria-invalid", "false")


def test_invalid_submit_is_blocked(goto_feature):
    page = goto_feature("forms")
    page.get_by_test_id("form-email").fill("nope")
    page.get_by_test_id("form-submit").click()
    expect(page.get_by_test_id("form-result")).to_have_text("")


def test_valid_submit(goto_feature):
    page = goto_feature("forms")
    page.get_by_test_id("form-name").fill("Ada")
    page.get_by_test_id("form-email").fill("ada@example.com")
    page.get_by_test_id("form-sub").check()
    page.get_by_test_id("form-choice").select_option("a")
    page.get_by_test_id("form-submit").click()
    expect(page.get_by_test_id("form-result")).to_have_text("name=Ada;email=ada@example.com;subscribe=True;choice=a")
