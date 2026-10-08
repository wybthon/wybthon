"""Smoke test that the browser + Pyodide path boots the E2E fixture app.

The heavy lifting happens in ``conftest.py``: the session-scoped
``fixture_page`` fixture serves the fixture project through ``wyb dev``,
boots Pyodide once, and fails fast if the bootstrap records a boot error.
This module just asserts the booted app is alive and navigable.
"""

import pytest


@pytest.mark.e2e
def test_fixture_app_bootstraps_pyodide(fixture_page):
    """Verifies Pyodide booted and the fixture app shell rendered."""
    assert fixture_page.evaluate("() => window.__WYB.status") == "ready"
    fixture_page.wait_for_selector("[data-testid=app-ready]")


@pytest.mark.e2e
def test_fixture_runs_in_dev_mode(fixture_page):
    """`wyb dev` builds a development bundle: dev-mode checks stay on."""
    code = "import wybthon; wybthon.is_dev_mode()"
    assert fixture_page.evaluate("(code) => window.__WYB.pyodide.runPython(code)", code) is True


@pytest.mark.e2e
def test_fixture_app_navigates(goto_feature):
    """Navigates to a feature route to confirm the router is functional."""
    page = goto_feature("reactivity")
    page.wait_for_selector("[data-testid=page-reactivity]")
