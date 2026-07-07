"""E2E: components (reactive props without remount, forward_ref, lifecycle)."""

import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e


def test_reactive_prop_no_remount(goto_feature):
    page = goto_feature("components")
    expect(page.get_by_test_id("comp-display")).to_have_text("hello")
    expect(page.get_by_test_id("comp-display-mounts")).to_have_text("1")

    page.get_by_test_id("comp-label-btn").click()
    expect(page.get_by_test_id("comp-display")).to_have_text("world")
    # Prop change updates the child in place; it is not remounted.
    expect(page.get_by_test_id("comp-display-mounts")).to_have_text("1")


def test_forward_ref(goto_feature):
    page = goto_feature("components")
    expect(page.get_by_test_id("comp-ref-attached")).to_have_text("yes")
    expect(page.get_by_test_id("comp-ref-input")).to_have_count(1)


def test_children_passthrough(goto_feature):
    page = goto_feature("components")
    expect(page.locator("[data-testid=comp-card] [data-testid=comp-card-child]")).to_have_text("inside")


def test_lifecycle_mount_cleanup(goto_feature):
    page = goto_feature("components")
    expect(page.get_by_test_id("comp-life")).to_have_text("alive")
    expect(page.get_by_test_id("comp-life-mounts")).to_have_text("1")
    expect(page.get_by_test_id("comp-life-cleanups")).to_have_text("0")

    page.get_by_test_id("comp-life-toggle").click()
    expect(page.get_by_test_id("comp-life")).to_have_count(0)
    expect(page.get_by_test_id("comp-life-cleanups")).to_have_text("1")

    page.get_by_test_id("comp-life-toggle").click()
    expect(page.get_by_test_id("comp-life")).to_have_text("alive")
    expect(page.get_by_test_id("comp-life-mounts")).to_have_text("2")
