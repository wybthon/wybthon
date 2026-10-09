"""The HTML parser's content rules that compiled markup must respect.

Templates (`wybthon.templates`) and compiled helper shapes
(`wybthon._shapes`) hand their static markup to the browser's HTML parser
and count on getting back exactly the nodes they serialized. The parser
rewrites some markup (it closes a `<p>` before a `<div>`, inserts a
`<tbody>`, moves text out of a table), so both compilers check these
rules first. Server rendering and the test DOM use the same element sets
to serialize and parse.
"""

from __future__ import annotations

__all__: list[str] = []

# Elements with no content and no end tag.
VOID_ELEMENTS = frozenset(
    {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
)

# Elements whose content the parser reads as text (or keeps out of the
# element's child list), so compiled markup can't put nodes inside them.
RAW_CONTENT_ELEMENTS = frozenset({"script", "style", "textarea", "title", "xmp", "iframe", "noscript", "template"})

# Elements whose text content serializes without escaping.
RAW_TEXT_ELEMENTS = frozenset({"script", "style", "xmp", "iframe", "noembed", "noframes", "noscript"})

# The parser drops one newline that immediately follows these start tags.
LEADING_NEWLINE_ELEMENTS = frozenset({"pre", "textarea", "listing"})

# Namespace roots. SVG and MathML mount with per-node namespaced commands:
# the HTML parser only preserves the case of attribute names it knows.
FOREIGN_ELEMENTS = frozenset({"svg", "math"})

# Elements whose content model forbids text (the parser would move it out).
NO_TEXT_CONTENT = frozenset({"table", "thead", "tbody", "tfoot", "tr", "colgroup", "select", "optgroup", "html"})

# Content models the parser enforces by inserting implied elements or
# dropping illegal ones.
ALLOWED_CHILDREN = {
    "table": frozenset({"caption", "colgroup", "thead", "tbody", "tfoot"}),
    "thead": frozenset({"tr"}),
    "tbody": frozenset({"tr"}),
    "tfoot": frozenset({"tr"}),
    "tr": frozenset({"td", "th"}),
    "select": frozenset({"option", "optgroup", "hr"}),
    "optgroup": frozenset({"option"}),
    "colgroup": frozenset({"col"}),
}

# Start tags that implicitly close an open `<p>`.
P_CLOSERS = frozenset(
    {
        "address",
        "article",
        "aside",
        "blockquote",
        "details",
        "dialog",
        "div",
        "dl",
        "fieldset",
        "figcaption",
        "figure",
        "footer",
        "form",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "hgroup",
        "hr",
        "main",
        "menu",
        "nav",
        "ol",
        "p",
        "pre",
        "search",
        "section",
        "table",
        "ul",
    }
)

# Elements the parser closes when the same element opens anywhere inside them.
NO_NESTED_DESCENDANT = frozenset({"a", "button", "form"})

# Elements the parser closes when the same element (or, for headings, any
# heading) opens directly inside them.
NO_NESTED_CHILD = frozenset({"li", "dt", "dd", "option", "h1", "h2", "h3", "h4", "h5", "h6"})

HEADINGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})
