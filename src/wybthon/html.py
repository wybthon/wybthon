"""Pythonic HTML element helpers that wrap the ``h()`` function.

Instead of writing::

    h("div", {"class": "card", "on_click": handler}, h("p", {}, "Hello"))

you can write::

    div(p("Hello"), class_name="card", on_click=handler)

Children are positional arguments, props are keyword arguments.

Prop name mapping:

- ``class_name`` → ``class`` (Python reserved word)
- ``html_for`` → ``for`` (Python reserved word)
- All other kwargs pass through unchanged.
"""

from typing import Any, Callable

from .vnode import Fragment, VNode, h

__all__ = [
    "Fragment",
    # Layout
    "div",
    "span",
    "section",
    "article",
    "aside",
    "header",
    "footer",
    "main_",
    "nav",
    # Headings
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    # Text
    "p",
    "a",
    "strong",
    "em",
    "small",
    "code",
    "pre",
    "br",
    "hr",
    "blockquote",
    # Lists
    "ul",
    "ol",
    "li",
    # Tables
    "table",
    "thead",
    "tbody",
    "tr",
    "th",
    "td",
    "caption",
    # Forms
    "form",
    "input_",
    "textarea",
    "select",
    "option",
    "button",
    "label",
    "fieldset",
    "legend",
    # Media
    "img",
    "video",
    "audio",
    "source",
    "canvas",
    # Interactive
    "details",
    "summary",
    "dialog",
    # Semantic
    "figure",
    "figcaption",
]


def _process_props(kwargs: dict) -> dict:
    """Convert Python keyword arguments to a VNode props dict.

    Maps ``class_name`` to ``class`` and ``html_for`` to ``for`` since
    those are reserved words in Python.
    """
    props: dict = {}
    for key, value in kwargs.items():
        if key == "class_name":
            props["class"] = value
        elif key == "html_for":
            props["for"] = value
        else:
            props[key] = value
    return props


def _el(tag: str) -> Callable[..., VNode]:
    """Create a helper function for the given HTML tag name."""

    def element_fn(*children: Any, **props: Any) -> VNode:
        return h(tag, _process_props(props), *children)

    element_fn.__name__ = tag
    element_fn.__qualname__ = tag
    element_fn.__doc__ = f"Create a ``<{tag}>`` element. Children are positional args, props are keyword args."
    return element_fn


# Layout / Structure
div = _el("div")
span = _el("span")
section = _el("section")
article = _el("article")
aside = _el("aside")
header = _el("header")
footer = _el("footer")
main_ = _el("main")
nav = _el("nav")

# Headings
h1 = _el("h1")
h2 = _el("h2")
h3 = _el("h3")
h4 = _el("h4")
h5 = _el("h5")
h6 = _el("h6")

# Text
p = _el("p")
a = _el("a")
strong = _el("strong")
em = _el("em")
small = _el("small")
code = _el("code")
pre = _el("pre")
br = _el("br")
hr = _el("hr")
blockquote = _el("blockquote")

# Lists
ul = _el("ul")
ol = _el("ol")
li = _el("li")

# Tables
table = _el("table")
thead = _el("thead")
tbody = _el("tbody")
tr = _el("tr")
th = _el("th")
td = _el("td")
caption = _el("caption")

# Forms
form = _el("form")
input_ = _el("input")
textarea = _el("textarea")
select = _el("select")
option = _el("option")
button = _el("button")
label = _el("label")
fieldset = _el("fieldset")
legend = _el("legend")

# Media
img = _el("img")
video = _el("video")
audio = _el("audio")
source = _el("source")
canvas = _el("canvas")

# Interactive
details = _el("details")
summary = _el("summary")
dialog = _el("dialog")

# Semantic
figure = _el("figure")
figcaption = _el("figcaption")
