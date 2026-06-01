"""E2E: reactive props (class, style, dataset) and controlled inputs."""

import re

import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e


def test_reactive_class(goto_feature):
    page = goto_feature("props")
    expect(page.get_by_test_id("props-class")).to_have_class("pill")
    page.get_by_test_id("props-class-btn").click()
    expect(page.get_by_test_id("props-class")).to_have_class("pill danger")


def test_reactive_style(goto_feature):
    page = goto_feature("props")
    expect(page.get_by_test_id("props-style")).to_have_attribute("style", re.compile("teal"))
    page.get_by_test_id("props-style-btn").click()
    expect(page.get_by_test_id("props-style")).to_have_attribute("style", re.compile("red"))


def test_reactive_dataset_attribute(goto_feature):
    page = goto_feature("props")
    expect(page.get_by_test_id("props-attr")).to_have_attribute("data-state", "idle")
    page.get_by_test_id("props-attr-btn").click()
    expect(page.get_by_test_id("props-attr")).to_have_attribute("data-state", "busy")


def test_controlled_input(goto_feature):
    page = goto_feature("props")
    page.get_by_test_id("props-input").fill("typed")
    expect(page.get_by_test_id("props-input-echo")).to_have_text("typed")
    # Controlled: a programmatic signal write drives the input value.
    page.get_by_test_id("props-input-set").click()
    expect(page.get_by_test_id("props-input")).to_have_value("hello")
    expect(page.get_by_test_id("props-input-echo")).to_have_text("hello")


def test_controlled_checkbox(goto_feature):
    page = goto_feature("props")
    expect(page.get_by_test_id("props-check-echo")).to_have_text("off")
    page.get_by_test_id("props-check").check()
    expect(page.get_by_test_id("props-check-echo")).to_have_text("on")
