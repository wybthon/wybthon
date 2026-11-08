"""Engine v9 (RFC 0010): components and control flow at the cost of their markup, and one-command hydration."""

from typing import Any

import pytest
from test_ssr import hydrate_from, nodes, visible

from wybthon import (
    For,
    NoHydration,
    ParentProps,
    Props,
    Show,
    component,
    create_signal,
    create_store,
    flush,
    html,
)
from wybthon.diagnostics import profile
from wybthon.kernel import (
    OP_CLAIM_ELEMENT,
    OP_CLAIM_SLOT,
    OP_CLAIM_TEXT,
    OP_CLAIM_TPL,
    OP_CLONE,
    OP_CREATE_COMMENT,
    OP_INSERT,
    OP_SET_ATTR,
)
from wybthon.reactivity import _core
from wybthon.server import render_to_string


class CardProps(ParentProps):
    title: str
    count: int = 0


@component
def Card(props: CardProps):
    return html(t'<div class="card"><h3>{props.title}</h3><span>{props.count}</span>{props.children}</div>')


@component
def Toggle(props: CardProps):
    open_, set_open = create_signal(False)

    def flip() -> None:
        set_open(lambda v: not v)

    return html(t"""<div class="toggle">
      <button onclick={flip}>{props.title}</button>{Show(open_(), html(t"<p>open</p>"))}
    </div>""")


def comments(root: Any) -> int:
    return sum(1 for n in nodes(root) if getattr(n, "_is_comment", False))


def element_texts(root: Any) -> list[str]:
    return [n.tag for n in nodes(root) if getattr(n, "tag", None)]


# ---------------------------------------------------------------------------
# Components and regions on the clone path
# ---------------------------------------------------------------------------


def test_a_component_row_sends_a_clone_per_template_and_nothing_else(wyb, root_element):
    items, set_items = create_signal([])

    def row(item, index):
        return html(t"<{Card} title={item['label']} count={item['id']}><em>{item['id']}</em></{Card}>")

    wyb["reconciler"].render(html(t"<section>{For(items(), row)}</section>"), root_element)
    with profile() as measured:
        set_items([{"id": i, "label": f"row {i}"} for i in range(10)])
        flush()
    # One clone for the card and one for its child: no fragment markers
    # around a single child, no hole anchor of its own for the component.
    assert measured.counts[f"op_{OP_CLONE}"] == 20
    assert measured.counts[f"op_{OP_CREATE_COMMENT}"] == 0
    assert measured.counts[f"op_{OP_INSERT}"] == 0
    assert visible(root_element.element) == "".join(f"row {i}{i}{i}" for i in range(10))


def test_show_in_a_slot_creates_no_markers_and_still_toggles(wyb, root_element):
    wyb["reconciler"].render(Toggle(title="t"), root_element)
    root = root_element.element
    before = comments(root)
    button = next(n for n in nodes(root) if getattr(n, "tag", None) == "button")
    for expected in ("topen", "t", "topen"):
        wyb["kernel"]._backend.dispatch("click", button)
        flush()
        assert visible(root) == expected
        # The branch reuses the slot's placeholder as its end: no markers.
        assert comments(root) == before


def test_for_in_a_slot_is_anchored_and_reorders_and_clears(wyb, root_element):
    items, set_items = create_signal(["a", "b", "c"])
    view = html(t"<ul>{For(items(), lambda item: html(t'<li>{item}</li>'))}<li>end</li></ul>")
    wyb["reconciler"].render(view, root_element)
    root = root_element.element
    assert visible(root) == "abcend"
    set_items(["c", "a", "b"])
    flush()
    assert visible(root) == "cabend"
    set_items([])
    flush()
    assert visible(root) == "end"
    set_items(["x"])
    flush()
    assert visible(root) == "xend"


def test_a_hole_switching_between_an_anchored_region_and_text(wyb, root_element):
    mode, set_mode = create_signal("list")

    def content() -> Any:
        if mode() == "list":
            return For(["a", "b"], lambda item: html(t"<i>{item}</i>"))
        if mode() == "show":
            return Show(True, html(t"<b>shown</b>"))
        return "text"

    wyb["reconciler"].render(html(t"<p>[{content()}]</p>"), root_element)
    root = root_element.element
    assert visible(root) == "[ab]"
    for value, expected in (("show", "[shown]"), ("text", "[text]"), ("list", "[ab]"), ("show", "[shown]")):
        set_mode(value)
        flush()
        assert visible(root) == expected


# ---------------------------------------------------------------------------
# Hydration
# ---------------------------------------------------------------------------


class CountingHydration:
    """Counts each kind of command a hydration sends."""

    def __init__(self, wyb: dict[str, Any], view: Any) -> None:
        self.html = render_to_string(view())
        self.counts: dict[int, int] = {}
        backend_apply = wyb["kernel"].PythonBackend.apply
        counts = self.counts

        def counting(backend: Any, ops: Any) -> None:
            for op in ops:
                counts[op[0]] = counts.get(op[0], 0) + 1
            backend_apply(backend, ops)

        wyb["kernel"].PythonBackend.apply = counting
        try:
            self.result = hydrate_from(wyb, self.html, view())
        finally:
            wyb["kernel"].PythonBackend.apply = backend_apply


def test_a_template_instance_hydrates_with_one_claim(wyb):
    rows = [{"id": i, "label": f"row {i}"} for i in range(5)]

    def view() -> Any:
        def row(item, index):
            return html(t'<div class="r"><h3>{item["label"]}</h3><span>{item["id"]}</span><em>x</em></div>')

        return html(t"<section>{For(rows, row)}</section>")

    hydration = CountingHydration(wyb, view)
    assert hydration.result.mismatches == 0
    assert hydration.result.created_elements == []
    # The section and each row: no per-node claims at all.
    assert hydration.counts.get(OP_CLAIM_TPL) == 6
    assert OP_CLAIM_ELEMENT not in hydration.counts and OP_CLAIM_TEXT not in hydration.counts
    # Only the section's slot holds nodes.
    assert hydration.counts.get(OP_CLAIM_SLOT) == 1
    assert visible(hydration.result.container) == "".join(f"row {i}{i}x" for i in range(5))


def test_components_and_show_hydrate_by_claim_and_stay_interactive(wyb):
    def view() -> Any:
        return html(t"""<main><{Card} title="One" count={1}><p>child</p></{Card}><{Toggle} title="t" /></main>""")

    hydration = CountingHydration(wyb, view)
    result = hydration.result
    assert result.mismatches == 0
    assert result.created_elements == []
    assert OP_CLAIM_ELEMENT not in hydration.counts
    assert visible(result.container) == "One1childt"
    button = next(n for n in nodes(result.container) if getattr(n, "tag", None) == "button")
    result.backend.dispatch("click", button)
    flush()
    assert visible(result.container) == "One1childtopen"


def test_hydration_sends_attribute_values_in_the_claim(wyb):
    selected, set_selected = create_signal(1)
    rows = [{"id": i, "label": f"row {i}"} for i in range(3)]

    def view() -> Any:
        def row(item, index):
            return html(
                t"""<tr class={"danger" if selected() == item["id"] else ""}>
                  <td><a href={"/rows/" + str(item["id"])}>{item["label"]}</a></td>
                </tr>"""
            )

        return html(t"<table><tbody>{For(rows, row)}</tbody></table>")

    hydration = CountingHydration(wyb, view)
    result = hydration.result
    assert result.mismatches == 0
    assert OP_SET_ATTR not in hydration.counts
    trs = [n for n in nodes(result.container) if getattr(n, "tag", None) == "tr"]
    assert [tr.attributes.get("class") for tr in trs] == [None, "danger", None]
    set_selected(2)
    flush()
    assert [tr.attributes.get("class") for tr in trs] == [None, None, "danger"]


def test_hydration_corrects_attribute_values_only_the_browser_computes(wyb):
    renders: list[int] = []

    def view() -> Any:
        # The server renders first; the browser computes other values (a
        # stored theme, say).
        renders.append(1)
        browser = len(renders) > 1
        theme = "dark" if browser else "light"
        color = "white" if browser else "black"
        return html(t"<main class={theme} style={ {'color': color} }>x</main>")

    hydration = CountingHydration(wyb, view)
    result = hydration.result
    assert hydration.counts.get(OP_CLAIM_TPL) == 1
    assert OP_SET_ATTR not in hydration.counts
    main = next(n for n in nodes(result.container) if getattr(n, "tag", None) == "main")
    assert main.getAttribute("class") == "dark"
    assert main.style.getPropertyValue("color") == "white"


def test_a_show_over_children_reopens(wyb, root_element):
    open_, set_open = create_signal(True)

    @component
    def Collapsible(props: ParentProps):
        return html(t"<div>{Show(open_, lambda: props.children)}</div>")

    wyb["reconciler"].render(html(t"<main><{Collapsible}><b>hi {1}</b></{Collapsible}></main>"), root_element)
    flush()
    for value, expected in ((False, ""), (True, "hi 1"), (False, ""), (True, "hi 1")):
        set_open(value)
        flush()
        assert visible(root_element.element) == expected


def test_a_keyed_list_keeps_its_items_through_one_item(wyb, root_element):
    ids, set_ids = create_signal([1])
    setups: list[int] = []

    class ItemProps(Props):
        n: int

    @component
    def Item(props: ItemProps):
        setups.append(props.n)
        return html(t"<i>{props.n}</i>")

    wyb["reconciler"].render(html(t"<p>{[Item(n=i, key=i) for i in ids()]}</p>"), root_element)
    flush()
    for value, expected in (([1, 2], "12"), ([1], "1"), ([2, 1], "21")):
        set_ids(value)
        flush()
        assert visible(root_element.element) == expected
    # Item 1 is set up once and kept; Item 2 is set up each time it comes back.
    assert setups == [1, 2, 2]


def test_text_next_to_static_text_adopts_the_server_text(wyb):
    count, set_count = create_signal(3)

    def view() -> Any:
        return html(t"<p>Count: {count} items</p>")

    hydration = CountingHydration(wyb, view)
    result = hydration.result
    assert result.mismatches == 0
    # The server's text is the slot's text node now, split off the static text
    # around it; the slot's `$` placeholder is gone.
    p = next(n for n in nodes(result.container) if getattr(n, "tag", None) == "p")
    assert [child.nodeValue for child in p.childNodes] == ["Count: ", "3", " items"]
    assert comments(p) == 0
    set_count(4)
    flush()
    assert visible(result.container) == "Count: 4 items"


def test_hydrated_dom_matches_a_client_render(wyb, root_element):
    def view() -> Any:
        return html(t"""<main>
          <{Card} title="A" count={2}><p>one</p><p>two</p></{Card}>
          <ul>{For(["x", "y"], lambda item: html(t"<li>{item}</li>"))}</ul>
          {Show(True, html(t"<b>shown</b>"))}
          <p>tail {"text"}</p>
        </main>""")

    result = hydrate_from(wyb, render_to_string(view()), view())
    assert result.mismatches == 0
    wyb["reconciler"].render(view(), root_element)

    def shape(root: Any) -> list[Any]:
        return [
            ("#comment" if getattr(n, "_is_comment", False) else n.tag or "#text", None if n.tag else n.nodeValue)
            for n in nodes(root)[1:]
            if not getattr(n, "_is_comment", False) and (n.tag or n.nodeValue)
        ]

    assert shape(result.container) == shape(root_element.element)


def test_a_mismatched_server_instance_is_rebuilt_in_place(wyb):
    def view() -> Any:
        return html(t'<div class="r"><h3>{"title"}</h3><span>{"body"}</span></div>')

    out = render_to_string(view()).replace("<span>body</span>", "<b>other</b>")
    result = hydrate_from(wyb, out, view())
    assert result.mismatches >= 1
    assert visible(result.container) == "titlebody"
    assert [n.tag for n in nodes(result.container) if n.tag] == ["div", "div", "h3", "span"]


def test_no_hydration_content_has_no_slot_markers(wyb):
    out = render_to_string(html(t"<div>{NoHydration(html(t'<p>a {1} b</p>'))}</div>"))
    inner = out[out.index("wyb:nh") : out.index("/wyb:nh")]
    assert "<!--$-->" not in inner


# ---------------------------------------------------------------------------
# The static probe
# ---------------------------------------------------------------------------


def test_a_reactive_expression_is_probed_once_per_template(wyb, root_element):
    store, set_store = create_store([{"label": f"r{i}"} for i in range(5)])
    calls = []
    probe = _core._probe

    def counting(fn: Any) -> Any:
        calls.append(fn)
        return probe(fn)

    _core._probe = counting
    try:
        wyb["reconciler"].render(
            html(t"<ul>{For(lambda: store, lambda row: html(t'<li>{row["label"]}</li>'))}</ul>"), root_element
        )
    finally:
        _core._probe = probe
    # The first row's probe found a reactive read; later rows bind directly.
    assert len(calls) == 1
    assert visible(root_element.element) == "r0r1r2r3r4"
    set_store(lambda rows: rows[2].update(label="changed"))
    flush()
    assert visible(root_element.element) == "r0r1changedr3r4"


def test_an_expression_that_was_reactive_is_probed_again_once_static(wyb, root_element):
    store, _ = create_store([{"label": "live"}])
    values: list[Any] = [store[0], {"label": "static"}, {"label": "static"}]
    calls = []
    probe = _core._probe

    def counting(fn: Any) -> Any:
        calls.append(fn)
        return probe(fn)

    def row(item, index):
        return html(t"<i>{item['label']}</i>")

    _core._probe = counting
    try:
        wyb["reconciler"].render(html(t"<p>{For(values, row)}</p>"), root_element)
    finally:
        _core._probe = probe
    assert visible(root_element.element) == "livestaticstatic"
    # The first row escaped; the second bound without a probe, read nothing,
    # and so cleared the mark; the third was probed again.
    assert len(calls) == 2


def test_component_props_are_still_checked_in_dev_mode(wyb, root_element):
    class NameProps(Props):
        name: str

    @component
    def Named(props: NameProps):
        return html(t"<b>{props.name}</b>")

    with pytest.raises(TypeError):
        wyb["reconciler"].render(html(t"<p><{Named} nme='x' /></p>"), root_element)
