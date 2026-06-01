"""E2E: router params, query strings, wildcards, nested paths, not-found, active link."""

import re

import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e


def test_route_params(goto_feature):
    page = goto_feature("router")
    page.get_by_test_id("router-link-user").click()
    page.wait_for_selector("[data-testid=page-router-user]")
    expect(page.get_by_test_id("router-user-id")).to_have_text("42")


def test_query_string(goto_feature):
    page = goto_feature("router")
    page.get_by_test_id("router-link-search").click()
    page.wait_for_selector("[data-testid=page-router-search]")
    expect(page.get_by_test_id("router-search-q")).to_have_text("hello")


def test_wildcard(goto_feature):
    page = goto_feature("router")
    page.get_by_test_id("router-link-docs").click()
    page.wait_for_selector("[data-testid=page-router-docs]")
    expect(page.get_by_test_id("router-docs-rest")).to_have_text("guide/intro")


def test_nested_paths(goto_feature):
    page = goto_feature("router")
    page.get_by_test_id("router-link-parent").click()
    page.wait_for_selector("[data-testid=page-router-parent]")

    page = goto_feature("router")
    page.get_by_test_id("router-link-child").click()
    page.wait_for_selector("[data-testid=page-router-child]")


def test_not_found(goto_feature):
    page = goto_feature("router")
    page.get_by_test_id("router-link-missing").click()
    page.wait_for_selector("[data-testid=page-not-found]")


def test_active_nav_link(goto_feature):
    page = goto_feature("reactivity")
    expect(page.get_by_test_id("nav-reactivity")).to_have_class(re.compile(r"\bactive\b"))
    page = goto_feature("flow")
    expect(page.get_by_test_id("nav-flow")).to_have_class(re.compile(r"\bactive\b"))
    expect(page.get_by_test_id("nav-reactivity")).not_to_have_class(re.compile(r"\bactive\b"))
