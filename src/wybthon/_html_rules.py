"""The HTML parser's content rules that compiled markup must respect.

Templates (`wybthon.templates`) hand their static markup to the
browser's HTML parser and count on getting back exactly the nodes they
serialized. The parser rewrites some markup (it closes a `<p>` before a
`<div>`, inserts a `<tbody>`, moves text out of a table), so the
template compiler checks these rules first. Server rendering and the test DOM use the same element sets
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

# Start tags that implicitly close a `<p>` open in button scope, however deep.
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
        "dd",
        "dt",
        "header",
        "hgroup",
        "hr",
        "li",
        "listing",
        "main",
        "menu",
        "nav",
        "ol",
        "p",
        "plaintext",
        "pre",
        "search",
        "section",
        "table",
        "ul",
        "xmp",
    }
)

# Elements the parser closes when the same element opens anywhere inside them.
NO_NESTED_DESCENDANT = frozenset({"a", "button", "form"})

# Elements the parser closes when the same element (or, for headings, any
# heading) opens directly inside them.
NO_NESTED_CHILD = frozenset({"li", "dt", "dd", "option", "h1", "h2", "h3", "h4", "h5", "h6"})

HEADINGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})

# Elements that end "button scope": a `<p>` outside one of these is out of
# reach of a start tag inside it.
BUTTON_SCOPE_BOUNDARIES = frozenset(
    {"applet", "button", "caption", "html", "marquee", "object", "table", "td", "template", "th"}
    | {"foreignObject", "foreignobject", "desc", "title", "mi", "mo", "mn", "ms", "mtext", "annotation-xml"}
)

# The parser's "special" elements. An `<li>` (or `<dd>`/`<dt>`) start tag
# closes an open one unless a special element other than these three
# intervenes.
SPECIAL_ELEMENTS = frozenset(
    {
        "address",
        "applet",
        "area",
        "article",
        "aside",
        "base",
        "basefont",
        "bgsound",
        "blockquote",
        "body",
        "br",
        "button",
        "caption",
        "center",
        "col",
        "colgroup",
        "dd",
        "details",
        "dir",
        "div",
        "dl",
        "dt",
        "embed",
        "fieldset",
        "figcaption",
        "figure",
        "footer",
        "form",
        "frame",
        "frameset",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "head",
        "header",
        "hgroup",
        "hr",
        "html",
        "iframe",
        "img",
        "input",
        "keygen",
        "li",
        "link",
        "listing",
        "main",
        "marquee",
        "menu",
        "meta",
        "nav",
        "noembed",
        "noframes",
        "noscript",
        "object",
        "ol",
        "p",
        "param",
        "plaintext",
        "pre",
        "script",
        "search",
        "section",
        "select",
        "source",
        "style",
        "summary",
        "table",
        "tbody",
        "td",
        "template",
        "textarea",
        "tfoot",
        "th",
        "thead",
        "title",
        "tr",
        "track",
        "ul",
        "wbr",
        "xmp",
    }
)
_LIST_SCOPE_TRANSPARENT = frozenset({"address", "div", "p"})

# What's open above an element, for the closing rules that reach past
# its parent: `(p open in button scope, li open, dd or dt open)`.
type Scope = tuple[bool, bool, bool]
ROOT_SCOPE: Scope = (False, False, False)


def enter_scope(scope: Scope, tag: str) -> Scope:
    """The scope an element's children see, given the scope it was opened in."""
    p_open, li_open, dd_open = scope
    if tag == "p":
        p_open = True
    elif tag in BUTTON_SCOPE_BOUNDARIES:
        p_open = False
    if tag in SPECIAL_ELEMENTS and tag not in _LIST_SCOPE_TRANSPARENT:
        li_open = tag == "li"
        dd_open = tag == "dd" or tag == "dt"
    return (p_open, li_open, dd_open)


def scope_conflict(scope: Scope, tag: str) -> str | None:
    """Why the parser would close an open ancestor on seeing `tag` here, or `None`.

    A block start tag closes a `<p>` open in button scope even through
    inline elements (`<p><span><div>`), and an `<li>`, `<dd>`, or `<dt>`
    closes an open one unless a special element such as a list intervenes.
    """
    p_open, li_open, dd_open = scope
    if p_open and tag in P_CLOSERS:
        return f"<{tag}> can't be inside <p>; the HTML parser would close the <p>"
    if li_open and tag == "li":
        return "<li> can't be inside another <li> unless a list (<ul> or <ol>) wraps it; the parser would close it"
    if dd_open and (tag == "dd" or tag == "dt"):
        return f"<{tag}> can't be inside <dd> or <dt> unless a <dl> wraps it; the parser would close it"
    return None
