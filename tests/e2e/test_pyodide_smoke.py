"""Smoke test that the browser + Pyodide path boots the E2E fixture app.

The heavy lifting happens in ``conftest.py``: the session-scoped
``fixture_page`` fixture serves the repo through ``wyb dev``, boots
Pyodide once, and fails fast if ``bootstrap.js`` records a boot error.
This module just asserts the booted app is alive and navigable.
"""

import pytest


@pytest.mark.e2e
def test_fixture_app_bootstraps_pyodide(fixture_page):
    """Verifies Pyodide booted and the fixture app shell rendered."""
    assert fixture_page.evaluate("() => window.__WYB_E2E_READY") is True
    fixture_page.wait_for_selector("[data-testid=app-ready]")


@pytest.mark.e2e
def test_fixture_app_navigates(goto_feature):
    """Navigates to a feature route to confirm the router is functional."""
    page = goto_feature("reactivity")
    page.wait_for_selector("[data-testid=page-reactivity]")
