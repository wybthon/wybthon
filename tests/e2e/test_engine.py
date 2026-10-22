"""E2E: engine surface (zero-argument handlers, compiled expressions, typed component props)."""

import json

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


def test_compiled_expressions_update_text_and_attributes(goto_feature):
    page = goto_feature("engine")
    count = page.get_by_test_id("eng-t-count")
    expect(count).to_have_text("Count: 1 (doubled: 2)")
    expect(page.get_by_test_id("eng-t-memo")).to_have_text("Memo: 2")
    expect(page.get_by_test_id("eng-t-price")).to_have_text("Price: 3.50")
    expect(page.get_by_test_id("eng-t-static")).to_have_text("Hello, Ada!")
    attr = page.get_by_test_id("eng-t-attr")
    expect(attr).to_have_attribute("title", "count is 1")
    expect(attr).to_have_attribute("class", "item item-1")
    # Each compiled expression is its own hole: the text nodes are updated
    # in place, never replaced.
    nodes = count.evaluate_handle("el => [...el.childNodes]")

    page.get_by_test_id("eng-inc").click()
    expect(count).to_have_text("Count: 2 (doubled: 4)")
    expect(page.get_by_test_id("eng-t-memo")).to_have_text("Memo: 4")
    expect(attr).to_have_attribute("title", "count is 2")
    expect(attr).to_have_attribute("class", "item item-2")
    assert count.evaluate(
        "(el, nodes) => el.childNodes.length === nodes.length && nodes.every((n, i) => el.childNodes[i] === n)",
        nodes,
    )

    # A format spec folds into the getter.
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

    # A compiled getter, a signal, a derived expression, and a callback field.
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


def test_fixture_templates_are_precompiled_by_the_build(goto_feature):
    """`wyb dev` compiles the app's templates: each literal carries its parse tree and mount functions."""
    page = goto_feature("engine")
    result = json.loads(
        python(
            page,
            """
import json, sys
from wybthon.templates import Precompiled

entries = [
    value
    for name, module in list(sys.modules.items())
    if name == "app" or name.startswith("app.")
    for key, value in vars(module).items()
    if key.startswith("__wybthon_t") and isinstance(value, Precompiled)
]
from app.features import engine
json.dumps({
    "entries": len(entries),
    "loaded": sum(entry.entry is not None for entry in entries),
    "engine_loaded": all(
        value.entry is not None for key, value in vars(engine).items() if key.startswith("__wybthon_t")
    ),
})
""",
        )
    )
    assert result["entries"] > 30, result
    assert result["loaded"] > 10, result
    assert result["engine_loaded"], result
