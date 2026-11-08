"""SVG and MathML templates mount by cloning, under any parent."""

from wybthon import For, Show, component, create_signal, flush, html
from wybthon.testing import render
from wybthon.vnode import NS_MATHML, NS_SVG


def _walk(node):
    yield node
    for child in getattr(node, "childNodes", ()) or ():
        yield from _walk(child)


def test_an_svg_template_clones_with_namespaced_nodes():
    from wybthon import diagnostics

    with diagnostics.profile() as measured, render(html(t'<svg viewBox="0 0 10 10"><circle r={5} /></svg>')) as screen:
        svg = screen.container.childNodes[0]
        assert svg.namespaceURI == NS_SVG
        assert svg.attributes["viewBox"] == "0 0 10 10"
        circle = svg.childNodes[0]
        assert circle.namespaceURI == NS_SVG
        assert circle.attributes["r"] == "5"
    assert measured.as_dict()["template_clones"] == 1


def test_svg_names_keep_their_case_when_cloned():
    with render(
        html(t'<svg><defs><linearGradient id="g" gradientUnits="userSpaceOnUse"></linearGradient></defs></svg>')
    ) as screen:
        gradient = screen.container.childNodes[0].childNodes[0].childNodes[0]
        assert gradient.tag == "linearGradient"
        assert gradient.namespaceURI == NS_SVG
        assert gradient.attributes["gradientUnits"] == "userSpaceOnUse"


def test_a_name_the_parser_would_lowercase_mounts_node_by_node():
    from wybthon import diagnostics

    with diagnostics.profile() as measured, render(html(t'<svg><g customAttr="1"></g></svg>')) as screen:
        g = screen.container.childNodes[0].childNodes[0]
        assert g.attributes["customAttr"] == "1"
        assert g.namespaceURI == NS_SVG
    assert measured.as_dict().get("template_clones", 0) == 0


def test_a_template_mounted_under_an_svg_parent_is_parsed_in_svg():
    @component
    def Dot():
        return html(t'<circle r="2"></circle>')

    with render(html(t"<svg>{Dot()}<g>{Dot()}</g></svg>")) as screen:
        svg = screen.container.childNodes[0]
        circles = [n for n in _walk(svg) if getattr(n, "tag", None) == "circle"]
        assert len(circles) == 2
        assert all(c.namespaceURI == NS_SVG for c in circles)


def test_rows_and_branches_in_svg_keep_the_namespace():
    points, set_points = create_signal([1, 2, 3])
    shown, set_shown = create_signal(False)

    def point(x, _index):
        return html(t"<circle cx={x} r='1'></circle>")

    view = html(t"""
      <svg>
        <g>{For(points, point)}</g>
        {Show(shown(), html(t"<rect width='1'></rect>"))}
      </svg>
    """)
    with render(view) as screen:
        set_shown(True)
        set_points([1, 2, 3, 4])
        flush()
        svg = screen.container.childNodes[0]
        elements = [n for n in _walk(svg) if getattr(n, "tag", None) in ("circle", "rect")]
        assert len(elements) == 5
        assert all(e.namespaceURI == NS_SVG for e in elements)


def test_foreign_object_children_are_html():
    with render(html(t"<svg><foreignObject><div>{'hi'}</div></foreignObject></svg>")) as screen:
        fo = screen.container.childNodes[0].childNodes[0]
        assert fo.tag == "foreignObject"
        assert fo.namespaceURI == NS_SVG
        div = fo.childNodes[0]
        assert getattr(div, "namespaceURI", None) is None


def test_mathml_templates_clone_in_their_namespace():
    with render(html(t"<math><mi>{'x'}</mi></math>")) as screen:
        math = screen.container.childNodes[0]
        assert math.namespaceURI == NS_MATHML
        assert math.childNodes[0].namespaceURI == NS_MATHML
