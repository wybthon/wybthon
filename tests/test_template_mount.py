"""Tests for template-based mounting (serializer, wiring, and fallbacks)."""

from conftest import collect_texts

import wybthon as _wybthon_pkg  # noqa: F401
from wybthon.vnode import Fragment, VNode, dynamic, h

# ---------------------------------------------------------------------------
# build_plan (pure serialization; uses stubs because template.py imports props)
# ---------------------------------------------------------------------------


def test_build_plan_static_tree(wyb):
    template = wyb["template"]
    tree = h("div", {"class": "box"}, h("p", {}, "hello"), h("span", {"id": "x"}, "world"))
    plan = template.build_plan(tree)
    assert plan is not None
    # Text content is hoisted to SET_TEXT bindings (one-space placeholders)
    # so structurally-identical trees share one template.
    assert plan.html == '<div class="box"><p> </p><span id="x"> </span></div>'
    texts = [(k, val) for (_v, k, _n, val) in plan.bindings]
    assert texts == [(template.BIND_TEXT, "hello"), (template.BIND_TEXT, "world")]


def test_build_plan_shares_html_across_texts(wyb):
    template = wyb["template"]
    plan_a = template.build_plan(h("div", {}, h("p", {}, "one"), h("p", {}, "two")))
    plan_b = template.build_plan(h("div", {}, h("p", {}, "three"), h("p", {}, "four")))
    assert plan_a is not None and plan_b is not None
    assert plan_a.html == plan_b.html


def test_build_plan_collects_event_and_reactive_bindings(wyb):
    template = wyb["template"]
    handler = lambda e: None  # noqa: E731
    getter = lambda: "dyn"  # noqa: E731
    tree = h("div", {}, h("button", {"on_click": handler}, "go"), h("span", {"title": getter}, "x"))
    plan = template.build_plan(tree)
    assert plan is not None
    kinds = sorted(k for (_v, k, _n, _val) in plan.bindings if k != template.BIND_TEXT)
    assert kinds == [template.BIND_EVENT, template.BIND_REACTIVE]
    assert "on_click" not in plan.html
    assert "title" not in plan.html


def test_build_plan_placeholders_for_dynamic_children(wyb):
    template = wyb["template"]
    tree = h("p", {}, "Count: ", dynamic(lambda: "0"), h("b", {}, "!"))
    plan = template.build_plan(tree)
    assert plan is not None
    assert plan.html == "<p> <!----><b> </b></p>"


def test_build_plan_value_checked_become_prop_bindings(wyb):
    template = wyb["template"]
    tree = h(
        "form",
        {},
        h("input", {"value": "abc", "type": "text"}),
        h("input", {"type": "checkbox", "checked": True}),
    )
    plan = template.build_plan(tree)
    assert plan is not None
    assert "abc" not in plan.html
    names = {n for (_v, k, n, _val) in plan.bindings if k == template.BIND_PROP}
    assert names == {"value", "checked"}


def test_build_plan_rejects_adjacent_text(wyb):
    template = wyb["template"]
    tree = h("div", {}, h("span", {}, "a", "b"), h("span", {}, "c"), h("span", {}, "d"))
    assert template.build_plan(tree) is None


def test_build_plan_rejects_raw_text_elements(wyb):
    template = wyb["template"]
    tree = h("div", {}, h("textarea", {}, "content"), h("span", {}, "x"))
    assert template.build_plan(tree) is None


def test_build_plan_rejects_tiny_trees(wyb):
    template = wyb["template"]
    assert template.build_plan(h("span", {}, "x")) is None


def test_build_plan_escapes_html(wyb):
    template = wyb["template"]
    tree = h("div", {"title": 'a"b<c'}, h("p", {}, "1 < 2 & 3 > 2"), h("span", {}, "ok"))
    plan = template.build_plan(tree)
    assert plan is not None
    assert 'title="a&quot;b&lt;c"' in plan.html
    # Text is hoisted, never serialized: no escaping concerns in content.
    texts = [val for (_v, k, _n, val) in plan.bindings if k == template.BIND_TEXT]
    assert "1 < 2 & 3 > 2" in texts


def test_build_plan_serializes_style_and_dataset(wyb):
    template = wyb["template"]
    tree = h(
        "div",
        {"style": {"color": "red", "fontSize": "12px"}, "dataset": {"row": "1"}},
        h("p", {}, "a"),
        h("p", {}, "b"),
    )
    plan = template.build_plan(tree)
    assert plan is not None
    assert 'style="color:red;font-size:12px"' in plan.html
    assert 'data-row="1"' in plan.html


# ---------------------------------------------------------------------------
# End-to-end mounting through the template path
# ---------------------------------------------------------------------------


def test_template_mount_produces_working_tree(wyb, root_element):
    rec = wyb["reconciler"]
    reactivity = wyb["reactivity"]
    count, set_count = reactivity.create_signal(0)

    tree = h(
        "div",
        {"class": "app"},
        h("p", {}, "Count: ", count),
        h("ul", {}, h("li", {}, "a"), h("li", {}, "b")),
    )
    rec.render(tree, root_element)

    texts = collect_texts(root_element.element)
    assert "Count: " in texts and "0" in texts and "a" in texts and "b" in texts
    assert root_element.element.childNodes[0].attributes.get("class") == "app"

    set_count(7)
    assert "7" in collect_texts(root_element.element)


def test_template_mount_wires_events(wyb, root_element):
    rec = wyb["reconciler"]
    kernel = wyb["kernel"]
    clicks = []

    tree = h("div", {}, h("button", {"on_click": lambda e: clicks.append(1)}, "go"), h("span", {}, "x"))
    rec.render(tree, root_element)

    button_node = root_element.element.childNodes[0].childNodes[0]
    kernel._backend.dispatch("click", button_node)
    assert clicks == [1]


def test_template_mount_populates_all_els(wyb, root_element):
    rec = wyb["reconciler"]
    tree = h("div", {}, h("p", {}, "one"), h("p", {}, "two"))
    rec.render(tree, root_element)

    def check(vnode):
        assert vnode.el is not None
        for child in vnode.children:
            if isinstance(child, VNode):
                check(child)

    check(tree)


def test_template_mount_components_inside_static_tree(wyb, root_element):
    rec = wyb["reconciler"]

    def Child(props):
        return h("em", {}, "child!")

    tree = h("div", {}, h("p", {}, "before"), h(Child, {}), h("p", {}, "after"))
    rec.render(tree, root_element)
    texts = collect_texts(root_element.element)
    assert "before" in texts and "child!" in texts and "after" in texts


def test_template_fallback_when_unsupported(wyb, root_element):
    """Without template support, mounting falls back to per-node ops."""
    rec = wyb["reconciler"]
    wyb["kernel"]._backend.supports_html = lambda: False

    reactivity = wyb["reactivity"]
    count, set_count = reactivity.create_signal(1)
    tree = h("div", {}, h("p", {}, "n=", count), h("span", {}, "s"))
    rec.render(tree, root_element)
    assert "1" in collect_texts(root_element.element)
    set_count(2)
    assert "2" in collect_texts(root_element.element)


def test_template_mount_inside_fragment_and_show(wyb, root_element):
    rec = wyb["reconciler"]
    flow = wyb["flow"]
    reactivity = wyb["reactivity"]
    visible, set_visible = reactivity.create_signal(True)

    tree = Fragment(
        flow.Show(
            when=visible,
            children=lambda: h("div", {}, h("p", {}, "shown"), h("p", {}, "content")),
            fallback=lambda: h("p", {}, "hidden"),
        )
    )
    rec.render(tree, root_element)
    assert "shown" in collect_texts(root_element.element)

    set_visible(False)
    texts = collect_texts(root_element.element)
    assert "hidden" in texts and "shown" not in texts

    set_visible(True)
    assert "shown" in collect_texts(root_element.element)
