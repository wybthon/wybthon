"""Observable integration and registry contracts in the real JS backend.

The Python snippets these tests run in the page aren't compiled (they're
`runPythonAsync` source), so they build markup with `h()` or with
templates whose interpolations are names, which mean the same thing
compiled or not.
"""

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
root = render(h("div", {},
    h("input", {"id": "contract-input", "on_focus": focus, "ref": [ref, cleanup_ref]}),
    h("button", {"id": "contract-button", "on_click": clicked}, "Go"),
    h("select", {"multiple": True, "selected_values": selected, "id": "contract-select"},
      For(options, lambda value, index: h("option", {"value": value}, value))),
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
from string.templatelib import Template
for iteration in range(300):
    # Distinct literals exceed the kernel's bounded template cache.
    markup = Template(f'<div id="unique-{iteration}" class="shape-{iteration}"><span>x</span></div>')
    root = render(html(markup), "#contract-host")
    assert render(h("p", {}, "replacement"), "#contract-host") is root
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
from wybthon import create_store, h, on_cleanup, render
from wybthon.virtual import VirtualFor
host = document.createElement("section")
host.id = "virtual-host"
document.body.appendChild(host)
virtual_data, virtual_write = create_store([{"id": i} for i in range(10000)])
virtual_created, virtual_removed = [], []
def virtual_row(item, index):
    virtual_created.append(item.id)
    on_cleanup(lambda: virtual_removed.append(item.id))
    return h("p", {"data_virtual": item.id}, lambda: str(index()))
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
from wybthon import event, h, render
from wybthon.forms import bind_text, form_state
host = document.createElement("section")
host.id = "event-extra"
document.body.appendChild(host)
checks = []
field = form_state({"text": ""})["text"]
extra_root = render(h("div", {},
    h("button", {"id": "once-button", "on_click": event(lambda e: checks.append("once"), once=True)}, "Once"),
    h("div", {"id": "shadow-target", "on_ping": lambda e: checks.append(e.detail["answer"])}),
    h("div", {"id": "wheel-target", "on_wheel": event(lambda e: e.prevent_default(), passive=True)}),
    h("input", {"id": "composition-input", **bind_text(field)}),
    h("p", {"id": "composition-value"}, field.value),
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


def test_templates_match_expanded_generic_mounts(goto_feature):
    """A template mounted by cloning matches the generic tree it stands for, before and after updates."""
    page = goto_feature("contracts")
    python(
        page,
        """
from js import document
from wybthon import h, html, Fragment, create_signal, flush
from wybthon import reconciler, kernel
from wybthon.dom import Element
host = document.createElement("section")
reference_host = document.createElement("section")
document.body.append(host, reference_host)
container, reference_container = Element(node=host), Element(node=reference_host)
text, write_text = create_signal("initial")
clicked = []
def view(label="base", extra=False):
    handler = lambda e: clicked.append(label)
    figure = html(t'<svg><circle viewBox="0 0 2 2" /></svg>') if extra else None
    return html(t'<div class={label}><button onclick={handler}>{label}</button><span>{text}</span>{figure}</div>')
for _ in range(3):
    current = reconciler.render(view(), container)
    current.dispose()
fragment = h(Fragment, {"key": "fragment"}, h("span", {}, "first"), h("span", {}, "second"))
cases = [
    lambda: view(),
    lambda: view("changed"),
    lambda: view("base", True),
    lambda: html(t"<div>{fragment}<span>{text}</span></div>"),
    lambda: html(t"<table><tbody><tr><td>cell</td></tr></tbody></table>"),
    lambda: html(t"<div><input value={text}><span>controlled</span></div>"),
    lambda: html(t"<div><span>adjacent{'text'}</span><span>tail</span></div>"),
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
    assert str(host.innerHTML) == str(reference_host.innerHTML), (str(host.innerHTML), str(reference_host.innerHTML))
    write_text("updated")
    flush()
    assert str(host.innerHTML) == str(reference_host.innerHTML), (str(host.innerHTML), str(reference_host.innerHTML))
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
from wybthon import For, create_signal, flush, h, html, render
from wybthon import kernel
host = document.createElement("section")
host.id = "protocol-host"
document.body.appendChild(host)
proto_rows, set_proto_rows = create_signal([])
proto_clicked = []
def proto_row(item, index):
    row_id, label = item["id"], item["label"]
    pick = lambda: proto_clicked.append(row_id)
    return html(t'''
      <li data-proto={row_id}><span>{label}</span><button data-pick={row_id} onclick={pick}>pick</button></li>
    ''')
proto_backend = kernel._backend
proto_apply = proto_backend.apply
proto_ops = []
def spy(batch):
    proto_ops.extend(list(op) for op in batch)
    proto_apply(batch)
proto_backend.apply = spy
proto_root = render(h("ul", {}, For(proto_rows, proto_row)), "#protocol-host")
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


def test_clearing_a_list_keeps_focus_on_its_element_siblings(goto_feature):
    page = goto_feature("contracts")
    python(
        page,
        """
from js import document
from wybthon import For, create_signal, flush, h, render
from wybthon.dom import Element

focus_host = document.createElement("div")
document.body.appendChild(focus_host)
focus_rows, set_focus_rows = create_signal([])
focus_root = render(
    h("div", {},
      h("input", {"id": "focus-before"}),
      For(focus_rows, lambda item, index: h("p", {"data-focus-row": item["id"]}, item["id"])),
      h("textarea", {"id": "focus-after"})),
    Element(node=focus_host),
)
""",
    )
    for field in ("#focus-before", "#focus-after"):
        python(page, 'set_focus_rows([{"id": i} for i in range(20)])\nflush()')
        expect(page.locator("[data-focus-row]")).to_have_count(20)
        page.fill(field, "typed")
        page.focus(field)
        page.evaluate("field => document.querySelector(field).setSelectionRange(2, 2)", field)
        python(page, "set_focus_rows([])\nflush()")
        expect(page.locator("[data-focus-row]")).to_have_count(0)
        # The siblings stay in the document untouched: focus, caret, and value.
        state = page.evaluate(
            """field => {
                const node = document.querySelector(field);
                return [document.activeElement === node, node.selectionStart, node.value];
            }""",
            field,
        )
        assert state == [True, 2, "typed"], (field, state)
    python(page, "focus_root.dispose()\nflush()\nfocus_host.remove()")


def test_clearing_a_list_keeps_a_selection_in_its_text_sibling(goto_feature):
    page = goto_feature("contracts")
    python(
        page,
        """
from js import document
from wybthon import For, create_signal, flush, h, render
from wybthon.dom import Element

select_host = document.createElement("div")
document.body.appendChild(select_host)
select_rows, set_select_rows = create_signal([])
select_root = render(
    h("div", {"id": "select-parent"},
      "Total: 42 items",
      For(select_rows, lambda item, index: h("p", {"data-select-row": item}, item))),
    Element(node=select_host),
)
set_select_rows(["a", "b", "c"])
flush()
""",
    )
    expect(page.locator("[data-select-row]")).to_have_count(3)
    selected = page.evaluate(
        """() => {
            const label = [...document.getElementById("select-parent").childNodes]
                .find(node => node.nodeType === 3 && node.nodeValue !== "");
            const range = document.createRange();
            range.setStart(label, 0);
            range.setEnd(label, 5);
            const selection = getSelection();
            selection.removeAllRanges();
            selection.addRange(range);
            return selection.toString();
        }"""
    )
    assert selected == "Total"
    python(page, "set_select_rows([])\nflush()")
    expect(page.locator("[data-select-row]")).to_have_count(0)
    assert page.evaluate("() => getSelection().toString()") == "Total"
    page.evaluate("() => getSelection().removeAllRanges()")
    python(page, "select_root.dispose()\nflush()\nselect_host.remove()")


@pytest.mark.parametrize(
    "view",
    [
        'h("ul", {"id": "fill-list"}, fill_list)',
        "html(t'<ul id=\"fill-list\">{fill_list}</ul>')",
    ],
    ids=["h", "template"],
)
def test_a_list_that_fills_its_parent_clears_with_the_shortcut_and_refills(goto_feature, view):
    page = goto_feature("contracts")
    python(
        page,
        f"""
from js import document
from wybthon import For, create_signal, flush, h, html, render
from wybthon.dom import Element

fill_host = document.createElement("div")
document.body.appendChild(fill_host)
fill_rows, set_fill_rows = create_signal([])
fill_list = For(fill_rows, lambda item, index: h("li", {{}}, item))
fill_root = render({view}, Element(node=fill_host))
""",
    )
    # Count the kernel's `parent.textContent = ""` clears on this list.
    page.evaluate(
        """() => {
            const setter = Object.getOwnPropertyDescriptor(Node.prototype, "textContent").set;
            window.__fillClears = 0;
            Object.defineProperty(document.getElementById("fill-list"), "textContent", {
                configurable: true,
                set(value) {
                    window.__fillClears += 1;
                    setter.call(this, value);
                },
            });
        }"""
    )
    for round_ in range(2):
        python(page, f"set_fill_rows([f'{round_}-{{i}}' for i in range(30)])\nflush()")
        expect(page.locator("#fill-list li")).to_have_count(30)
        expect(page.locator("#fill-list li").first).to_have_text(f"{round_}-0")
        python(page, "set_fill_rows([])\nflush()")
        expect(page.locator("#fill-list li")).to_have_count(0)
        assert page.evaluate("() => window.__fillClears") == round_ + 1
        # Only the list's own markers survive the parent being emptied.
        survivors = page.evaluate(
            "() => [...document.getElementById('fill-list').childNodes].map(n => [n.nodeType, n.nodeValue])"
        )
        assert all(kind == 8 or (kind == 3 and text == "") for kind, text in survivors), survivors
    python(page, "fill_root.dispose()\nflush()\nfill_host.remove()")
