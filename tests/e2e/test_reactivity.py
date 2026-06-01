"""E2E: reactive primitives (signal, memo, effect, batch, untrack)."""

import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e


def test_signal_and_memo(goto_feature):
    page = goto_feature("reactivity")
    expect(page.get_by_test_id("rx-count")).to_have_text("0")
    expect(page.get_by_test_id("rx-doubled")).to_have_text("0")

    page.get_by_test_id("rx-inc").click()
    expect(page.get_by_test_id("rx-count")).to_have_text("1")
    expect(page.get_by_test_id("rx-doubled")).to_have_text("2")

    page.get_by_test_id("rx-inc").click()
    expect(page.get_by_test_id("rx-doubled")).to_have_text("4")

    page.get_by_test_id("rx-reset").click()
    expect(page.get_by_test_id("rx-count")).to_have_text("0")


def test_effect_runs_and_batch(goto_feature):
    page = goto_feature("reactivity")
    expect(page.get_by_test_id("rx-effect-runs")).to_have_text("1")

    page.get_by_test_id("rx-inc").click()
    expect(page.get_by_test_id("rx-effect-runs")).to_have_text("2")

    # A batch of two writes only triggers the effect once more.
    page.get_by_test_id("rx-batch").click()
    expect(page.get_by_test_id("rx-count")).to_have_text("3")
    expect(page.get_by_test_id("rx-effect-runs")).to_have_text("3")


def test_untrack(goto_feature):
    page = goto_feature("reactivity")
    expect(page.get_by_test_id("rx-untracked-runs")).to_have_text("1")

    # Writing the untracked signal does not re-run the effect.
    page.get_by_test_id("rx-set-b").click()
    expect(page.get_by_test_id("rx-untracked-runs")).to_have_text("1")

    # Writing the tracked signal does.
    page.get_by_test_id("rx-set-a").click()
    expect(page.get_by_test_id("rx-untracked-runs")).to_have_text("2")

    page.get_by_test_id("rx-set-b").click()
    expect(page.get_by_test_id("rx-untracked-runs")).to_have_text("2")
