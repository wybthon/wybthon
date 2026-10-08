"""Observable integration and registry contracts in the real JS backend."""

import json

import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e


def python(page, code):
    return page.evaluate("code => window.__WYB.pyodide.runPythonAsync(code)", code)


def test_edit_reorder_async_optimistic_error_and_unmount(goto_feature):
    page = goto_feature("contracts")
    first = page.locator('[data-row="1"]').element_handle()
    page.click('[data-testid="contract-edit"]')
    expect(page.locator('[data-row="1"]')).to_have_text("0:Augusta")
    page.click('[data-testid="contract-reverse"]')
    expect(page.locator('[data-row="1"]')).to_have_text("1:Augusta")
    assert first.evaluate("node => node === document.querySelector('[data-row=\"1\"]')")
    page.click('[data-testid="contract-filter"]')
    expect(page.locator('[data-testid="contract-pending"]')).to_have_text("True")
    expect(page.locator("[data-row]")).to_have_count(2)
    expect(page.locator("[data-row]")).to_have_count(1)
    page.click('[data-testid="contract-save"]')
    expect(page.locator('[data-testid="contract-saved"]')).to_have_text("1")
    expect(page.locator('[data-testid="contract-saving"]')).to_have_text("True")
    expect(page.locator('[data-testid="contract-saving"]')).to_have_text("False")
    expect(page.locator('[data-testid="contract-saved"]')).to_have_text("1")
    page.click('[data-testid="contract-error"]')
    expect(page.locator('[data-testid="contract-failure"]')).to_have_text("Filter failed")
    page.click('[data-testid="contract-recover"]')
    expect(page.locator("[data-row]")).to_have_count(1)
    page.click('[data-testid="contract-wait"]')
    page.click('[data-testid="nav-blank"]')
    expect(page.locator('[data-testid="page-blank"]')).to_be_visible()
    counts = json.loads(
        python(
            page,
            "import json\nfrom app.features import contracts\n"
            "json.dumps([contracts.mounted, contracts.removed, contracts.cancelled])",
        )
    )
    assert counts[0] == counts[1]
    assert counts[2] == 1


def test_browser_events_refs_selection_and_registry_lifetimes(goto_feature):
    page = goto_feature("events")
    python(
        page,
        """
import json, asyncio
from js import document
from wybthon import *
from wybthon import kernel
from wybthon.events import set_handler
from wybthon.testing import tick
host = document.createElement("section")
host.id = "contract-host"
document.body.appendChild(host)
checks = []
selected, select_write = create_signal(["b"])
options, options_write = create_signal(["a", "b"])
ref = Ref()
def cleanup_ref(element):
    checks.append("ref")
    return lambda: checks.append("ref-cleanup")
async def clicked(event):
    await asyncio.sleep(0)
    checks.append("async-click")
def focus(event):
    checks.append("focus")
root = render(div(
    input_(id="contract-input", on_focus=focus, ref=[ref, cleanup_ref]),
    button("Go", id="contract-button", on_click=clicked),
    select(For(options, lambda value, index: option(value, value=value)),
           multiple=True, selected_values=selected, id="contract-select"),
), "#contract-host")
""",
    )
    page.focus("#contract-input")
    page.click("#contract-button")
    assert json.loads(python(page, "await tick()\njson.dumps(checks)")) == ["ref", "focus", "async-click"]
    assert page.locator("#contract-select").evaluate("node => Array.from(node.selectedOptions, o => o.value)") == ["b"]
    python(page, 'options_write(["b", "c"]); select_write(["c"]); flush()')
    assert page.locator("#contract-select").evaluate("node => Array.from(node.selectedOptions, o => o.value)") == ["c"]
    python(
        page,
        """
node_id = kernel.adopt(document.querySelector("#contract-button"))
set_handler(node_id, "on_click", event(lambda e: checks.append("capture"), capture=True))
flush()
set_handler(node_id, "on_click", lambda e: checks.append("bubble"))
flush()
""",
    )
    page.click("#contract-button")
    assert json.loads(python(page, "json.dumps(checks)"))[-1] == "bubble"
    python(
        page,
        "root.dispose(); flush()\nassert ref.current is None\n"
        'assert checks[-1] == "ref-cleanup"\nregistry = kernel.stats()',
    )
    python(
        page,
        """
for iteration in range(300):
    # Distinct structural classes exceed the bounded template cache.
    root = render(div(span("x"), id=f"unique-{iteration}", class_=f"shape-{iteration}"), "#contract-host")
    assert render(p("replacement"), "#contract-host") is root
    assert host.textContent == "replacement"
    root.dispose()
flush()
assert kernel.stats()["nodes"] == registry["nodes"]
assert kernel.stats()["roots"] == registry["roots"]
assert kernel.stats()["listeners"] == registry["listeners"]
assert kernel.stats()["templates"] <= 256
host.remove()
""",
    )


def test_virtual_rows_scroll_and_dispose(goto_feature):
    page = goto_feature("flow")
    python(
        page,
        """
from js import document
from wybthon import create_store, on_cleanup, render, p
from wybthon.virtual import VirtualFor
host = document.createElement("section")
host.id = "virtual-host"
document.body.appendChild(host)
virtual_data, virtual_write = create_store([{"id": i} for i in range(10000)])
virtual_created, virtual_removed = [], []
def virtual_row(item, index):
    virtual_created.append(item.id)
    on_cleanup(lambda: virtual_removed.append(item.id))
    return p(lambda: str(index()), data_virtual=item.id)
virtual_root = render(
    VirtualFor(lambda: virtual_data, virtual_row, height=200, row_height=20, overscan=2, id="virtual-scroll"),
    "#virtual-host",
)
""",
    )
    assert page.locator("[data-virtual]").count() == 12
    page.locator("#virtual-scroll").evaluate(
        "node => { node.scrollTop = 2000; node.dispatchEvent(new Event('scroll')); }"
    )
    expect(page.locator('[data-virtual="98"]')).to_have_text("98")
    assert page.locator("[data-virtual]").count() == 14
    python(
        page,
        """
virtual_root.dispose()
assert sorted(virtual_created) == sorted(virtual_removed)
host.remove()
""",
    )


def test_native_options_composed_events_and_composition(goto_feature):
    page = goto_feature("events")
    python(
        page,
        """
import json
from js import document
from wybthon import button, div, event, input_, p, render
from wybthon.forms import bind_text, form_state
host = document.createElement("section")
host.id = "event-extra"
document.body.appendChild(host)
checks = []
field = form_state({"text": ""})["text"]
extra_root = render(div(
    button("Once", id="once-button", on_click=event(lambda e: checks.append("once"), once=True)),
    div(id="shadow-target", on_ping=lambda e: checks.append(e.detail["answer"])),
    div(id="wheel-target", on_wheel=event(lambda e: e.prevent_default(), passive=True)),
    input_(id="composition-input", **bind_text(field)),
    p(field.value, id="composition-value"),
), "#event-extra")
""",
    )
    page.click("#once-button")
    page.click("#once-button")
    page.locator("#shadow-target").evaluate("""node => {
        const shadow = node.attachShadow({mode: 'open'});
        const child = document.createElement('button');
        shadow.appendChild(child);
        child.dispatchEvent(new CustomEvent('ping', {bubbles: true, composed: true, detail: {answer: 42}}));
    }""")
    assert json.loads(python(page, "json.dumps(checks)")) == ["once", 42]
    assert page.locator("#wheel-target").evaluate(
        "node => node.dispatchEvent(new WheelEvent('wheel', {cancelable: true}))"
    )
    page.locator("#composition-input").evaluate("""node => {
        node.value = 'composed';
        node.dispatchEvent(new InputEvent('input', {bubbles: true, isComposing: true}));
    }""")
    expect(page.locator("#composition-value")).to_have_text("")
    page.locator("#composition-input").evaluate(
        "node => node.dispatchEvent(new CompositionEvent('compositionend', {bubbles: true}))"
    )
    expect(page.locator("#composition-value")).to_have_text("composed")
    python(page, "extra_root.dispose()\nhost.remove()")


def test_specialized_templates_match_native_generic_mounts(goto_feature):
    page = goto_feature("contracts")
    python(
        page,
        """
from js import document
from wybthon import div, span, h, Fragment, create_signal, flush
from wybthon import reconciler, kernel
from wybthon.dom import Element
host = document.createElement("section")
reference_host = document.createElement("section")
document.body.append(host, reference_host)
container, reference_container = Element(node=host), Element(node=reference_host)
text, write_text = create_signal("initial")
clicked = []
def view(label="base", extra=False):
    return div(
        h("button", {"on_click": lambda e: clicked.append(label)}, label),
        span(text),
        *([h("svg", {}, h("circle", {"viewBox": "0 0 2 2"}))] if extra else []),
        class_=label,
    )
for _ in range(3):
    current = reconciler.render(view(), container)
    current.dispose()
cases = [
    lambda: view(),
    lambda: view("changed"),
    lambda: view("base", True),
    lambda: div(h(Fragment, {"key": "fragment"}, span("first"), span("second")), span(text)),
    lambda: h("table", {}, h("tbody", {}, h("tr", {}, h("td", {}, "cell")))),
    lambda: div(h("input", {"value": text}), span("controlled")),
    lambda: div(span("adjacent", "text"), span("tail")),
]
templates_enabled = kernel.html_templates
assert templates_enabled is True
for make in cases:
    optimized = reconciler.render(make(), container)
    kernel.html_templates = False
    try:
        reference = reconciler.render(make(), reference_container)
    finally:
        kernel.html_templates = templates_enabled
    assert str(host.innerHTML) == str(reference_host.innerHTML)
    write_text("updated")
    flush()
    assert str(host.innerHTML) == str(reference_host.innerHTML)
    button = host.querySelector("button")
    if button:
        button.click()
        assert clicked[-1] == str(button.textContent)
    optimized.dispose()
    reference.dispose()
    assert not host.childNodes.length and not reference_host.childNodes.length
    write_text("initial")
    flush()
kernel.emit((kernel.OP_RELEASE, [container.node_id, reference_container.node_id]))
kernel.commit()
host.remove()
reference_host.remove()
""",
    )


def test_kernel_protocol_fused_clone_declared_listeners_and_native_disposal(goto_feature):
    page = goto_feature("contracts")
    python(
        page,
        """
import json
from js import document
from wybthon import For, button, create_signal, flush, li, render, span, ul
from wybthon import kernel
host = document.createElement("section")
host.id = "protocol-host"
document.body.appendChild(host)
proto_rows, set_proto_rows = create_signal([])
proto_clicked = []
def proto_row(item, index):
    return li(
        span(item["label"]),
        button("pick", on_click=lambda: proto_clicked.append(item["id"]), data_pick=item["id"]),
        data_proto=item["id"],
    )
proto_backend = kernel._backend
proto_apply = proto_backend.apply
proto_ops = []
def spy(batch):
    proto_ops.extend(list(op) for op in batch)
    proto_apply(batch)
proto_backend.apply = spy
proto_root = render(ul(For(proto_rows, proto_row)), "#protocol-host")
proto_baseline = kernel.stats()
proto_ops.clear()
set_proto_rows([{"id": i, "label": f"row {i}"} for i in range(50)])
flush()
""",
    )
    created = json.loads(python(page, "json.dumps([op[0] for op in proto_ops])"))
    expect(page.locator("[data-proto]")).to_have_count(50)
    expect(page.locator('[data-proto="7"] span')).to_have_text("row 7")
    # Each row mounts with one fused CLONE command; its click handler is
    # declared by the template registration, so no LISTEN commands go out.
    assert created.count(4) == 50, created  # OP_CLONE
    assert 11 not in created, created  # OP_LISTEN
    registered = json.loads(python(page, "json.dumps([op for op in proto_ops if op[0] == kernel.OP_REGISTER_TPL])"))
    assert any(["click" in [event for _, event in op[5]] for op in registered]), registered
    page.click('[data-pick="7"]')
    page.click('[data-pick="12"]')
    assert json.loads(python(page, "json.dumps(proto_clicked)")) == [7, 12]
    # Clearing the list is one native range disposal; the kernel releases
    # every registered node inside it.
    cleared = json.loads(
        python(
            page,
            """
proto_ops.clear()
set_proto_rows([])
flush()
json.dumps([op[0] for op in proto_ops])
""",
        )
    )
    assert cleared == [19], cleared  # OP_DISPOSE_RANGE
    expect(page.locator("[data-proto]")).to_have_count(0)
    stats = json.loads(python(page, "json.dumps([kernel.stats(), proto_baseline])"))
    for name in ("nodes", "listeners", "roots"):
        assert stats[0][name] == stats[1][name], (name, stats)
    python(
        page,
        """
del proto_backend.apply
proto_root.dispose()
flush()
host.remove()
""",
    )
