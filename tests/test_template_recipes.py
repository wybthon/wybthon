"""Repeated VDOM shapes retain instance data and fall back on structural edits."""

import gc
import weakref

import pytest
from conftest import StubNode, collect_texts

from wybthon import For, Fragment, Ref, create_signal, div, flush, h, span, template
from wybthon.diagnostics import profile


def test_repeated_templates_bind_each_instances_values_and_lifetimes(wyb, root_element):
    rows, set_rows = create_signal(list(range(20)))
    label, set_label = create_signal("first")
    refs, events = [], []

    def row(value, index):
        ref = Ref()
        refs.append(ref)
        return div(
            h("button", {"on_click": lambda e: events.append(value), "ref": ref}, str(value)),
            span(label),
            class_=lambda: "even" if value % 2 == 0 else "odd",
            data_row=value,
        )

    with profile() as measured:
        root = wyb["reconciler"].render(For(rows, row), root_element)
    assert measured.counts["template_recipe_hits"] >= 18
    for value, ref in enumerate(refs):
        button = ref.current.element
        assert button.childNodes[0].nodeValue == str(value)
        assert button.parentNode.attributes["data-row"] == str(value)
        wyb["kernel"]._backend.dispatch("click", button)
    assert events == list(range(20))
    set_label("second")
    flush()
    assert collect_texts(root_element.element).count("second") == 20
    set_rows([])
    flush()
    assert all(ref.current is None for ref in refs)
    root.dispose()


@pytest.mark.parametrize(
    "change",
    [
        lambda: div(span("x"), span("y"), class_="changed"),
        lambda: div(span("x"), span("y"), class_=lambda: "dynamic"),
        lambda: div(span("x"), span("y"), class_={"yes": True}),
        lambda: div(span("x"), span("y"), class_={"yes": lambda: True}),
        lambda: div(span("x"), span("y"), class_="base", id="added"),
        lambda: div(span("x"), span("y")),
        lambda: div(span("x"), h("strong", {}, "y"), class_="base"),
        lambda: div(span("x"), span("y"), span("z"), class_="base"),
        lambda: div(span("x"), class_="base"),
        lambda: div(span("x", "adjacent"), span("y"), class_="base"),
        lambda: div(span(None, False, 12), span(3.5), class_="base"),
        lambda: div(Fragment(span("x"), span("y")), class_="base"),
        lambda: div(span(lambda: "hole"), span("y"), class_="base"),
        lambda: div(h("svg", {}, h("circle", {"r": 2})), span("y"), class_="base"),
    ],
)
def test_shape_guards_match_the_generic_serializer(wyb, change):
    template._recent_recipes.clear()
    for _ in range(3):
        template.build_plan(div(span("x"), span("y"), class_="base"))
    actual = template.build_plan(change())
    expected = template._build_plan_uncached(change())
    assert (actual is None) == (expected is None)
    if actual is not None:
        assert actual.html == expected.html
        assert actual.node_count == expected.node_count
        assert [(kind, name) for _, kind, name, _ in actual.bindings] == [
            (kind, name) for _, kind, name, _ in expected.bindings
        ]


def test_recipe_normalization_preserves_dynamic_child_ownership(wyb, root_element):
    root = None
    for value in range(4):
        if root is not None:
            root.dispose()
        root = wyb["reconciler"].render(
            div(h(Fragment, {"key": "owned"}, span(str(value))), span(lambda: "dynamic")), root_element
        )
        assert [text for text in collect_texts(root_element.element) if text] == [str(value), "dynamic"]
    root.dispose()


def test_recipes_are_bounded_and_dont_retain_instance_objects(wyb, root_element):
    class Callback:
        def __call__(self, event):
            pass

    callback = Callback()
    reference = weakref.ref(callback)
    for index in range(300):
        for _ in range(2):
            tree = div(h("button", {"on_click": callback}, "go"), span("body"), class_=f"recipe-{index}")
            template.build_plan(tree)
    del tree, callback
    gc.collect()
    assert reference() is None
    assert len(template._recipes) <= template._RECIPE_CACHE_MAX
    assert len(template._recent_recipes) <= template._RECIPE_CACHE_MAX


def test_template_prop_names_are_data_and_never_generated_source(wyb, root_element):
    malicious = "x']; raise RuntimeError('interpolated'); #"
    for value in range(3):
        other = wyb["dom"].Element(node=StubNode(tag="div"))
        root = wyb["reconciler"].render(div(span("x"), span("y"), **{malicious: str(value)}), other)
        assert other.element.childNodes[0].attributes[malicious] == str(value)
        root.dispose()
