"""E2E: engine v2 surface (zero-argument handlers, t-strings, typed component props)."""

import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e


def python(page, code):
    return page.evaluate("code => window.__WYB.pyodide.runPythonAsync(code)", code)


def test_zero_argument_handlers(goto_feature):
    page = goto_feature("engine")
    expect(page.get_by_test_id("eng-taps")).to_have_text("0")
    page.get_by_test_id("eng-tap").click()
    expect(page.get_by_test_id("eng-taps")).to_have_text("1")
    page.get_by_test_id("eng-tap-lambda").click()
    expect(page.get_by_test_id("eng-taps")).to_have_text("11")
    # An async handler with no parameters runs to completion too.
    page.get_by_test_id("eng-tap-async").click()
    expect(page.get_by_test_id("eng-async-taps")).to_have_text("1")


def test_tstring_text_and_attributes_update(goto_feature):
    page = goto_feature("engine")
    expect(page.get_by_test_id("eng-t-count")).to_have_text("Count: 1 (doubled: 2)")
    expect(page.get_by_test_id("eng-t-price")).to_have_text("Price: 3.50")
    expect(page.get_by_test_id("eng-t-static")).to_have_text("Hello, Ada!")
    attr = page.get_by_test_id("eng-t-attr")
    expect(attr).to_have_attribute("title", "count is 1")
    expect(attr).to_have_attribute("class", "item item-1")
    # One binding per t-string: the text node is updated in place.
    text_node = page.get_by_test_id("eng-t-count").evaluate_handle("el => el.firstChild")

    page.get_by_test_id("eng-inc").click()
    expect(page.get_by_test_id("eng-t-count")).to_have_text("Count: 2 (doubled: 4)")
    expect(attr).to_have_attribute("title", "count is 2")
    expect(attr).to_have_attribute("class", "item item-2")
    assert page.get_by_test_id("eng-t-count").evaluate("(el, node) => el.firstChild === node", text_node)
    assert page.get_by_test_id("eng-t-count").evaluate("el => el.childNodes.length") == 1

    page.get_by_test_id("eng-price").click()
    expect(page.get_by_test_id("eng-t-price")).to_have_text("Price: 4.75")
    expect(page.get_by_test_id("eng-t-static")).to_have_text("Hello, Ada!")


def test_typed_component_receives_reactive_props(goto_feature):
    page = goto_feature("engine")
    mounts = python(page, "from app.features import engine\nengine.mounts")
    expect(page.get_by_test_id("eng-badge-label")).to_have_text("clicks")
    expect(page.get_by_test_id("eng-badge-count")).to_have_text("1")
    expect(page.get_by_test_id("eng-badge-t")).to_have_text("clicks=1 (cold)")
    expect(page.get_by_test_id("eng-badge-t")).to_have_class("tone-cold")
    # Defaults apply when the parent omits a prop; the plain test id field works.
    expect(page.get_by_test_id("eng-badge-static-count")).to_have_text("0")
    expect(page.get_by_test_id("eng-badge-static-t")).to_have_text("fixed=0 (plain)")

    # A signal, a derived zero-argument function, and a plain callback field.
    page.get_by_test_id("eng-inc").click()
    page.get_by_test_id("eng-inc").click()
    page.get_by_test_id("eng-rename").click()
    expect(page.get_by_test_id("eng-badge-label")).to_have_text("taps")
    expect(page.get_by_test_id("eng-badge-count")).to_have_text("3")
    expect(page.get_by_test_id("eng-badge-t")).to_have_text("taps=3 (hot)")
    expect(page.get_by_test_id("eng-badge-t")).to_have_class("tone-hot")
    # Reading the callback field never calls it; the child calls it on click.
    expect(page.get_by_test_id("eng-received")).to_have_text("none")
    page.get_by_test_id("eng-badge-ping").click()
    expect(page.get_by_test_id("eng-received")).to_have_text("ping 1")
    page.get_by_test_id("eng-badge-ping").click()
    expect(page.get_by_test_id("eng-received")).to_have_text("ping 2")
    # Prop updates flow into the mounted instances; nothing re-ran.
    assert python(page, "from app.features import engine\nengine.mounts") == mounts


def test_component_rejects_unknown_and_missing_props_in_dev(goto_feature):
    page = goto_feature("engine")
    result = python(
        page,
        """
import wybthon
from app.features.engine import Badge
errors = []
for call in (lambda: Badge(label="x", bogus=1), lambda: Badge(count=1)):
    try:
        call()
    except TypeError as exc:
        errors.append(str(exc))
f"{wybthon.is_dev_mode()}|{len(errors)}|{' / '.join(errors)}"
""",
    )
    dev, count, messages = result.split("|", 2)
    assert dev == "True"
    assert count == "2", messages
    assert "bogus" in messages
    assert "label" in messages
