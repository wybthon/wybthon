"""E2E: reactive stores (per-path tracking, nested set, functional set, produce)."""

import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e


def test_store_updates(goto_feature):
    page = goto_feature("stores")
    expect(page.get_by_test_id("store-count")).to_have_text("0")
    expect(page.get_by_test_id("store-name")).to_have_text("Ada")
    expect(page.get_by_test_id("store-todo")).to_have_text("False")
    expect(page.get_by_test_id("store-len")).to_have_text("1")

    page.get_by_test_id("store-inc").click()
    expect(page.get_by_test_id("store-count")).to_have_text("1")

    page.get_by_test_id("store-rename").click()
    expect(page.get_by_test_id("store-name")).to_have_text("Grace")

    page.get_by_test_id("store-toggle").click()
    expect(page.get_by_test_id("store-todo")).to_have_text("True")


def test_store_produce(goto_feature):
    page = goto_feature("stores")
    page.get_by_test_id("store-produce").click()
    expect(page.get_by_test_id("store-count")).to_have_text("1")

    page.get_by_test_id("store-add").click()
    expect(page.get_by_test_id("store-len")).to_have_text("2")
