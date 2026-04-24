"""Pythonic HTML element helpers that wrap [`h()`][wybthon.h].

These helpers let you author markup that reads more like Python than
hyperscript. Instead of writing:

```python
h("div", {"class": "card", "on_click": handler}, h("p", {}, "Hello"))
```

you can write:

```python
div(p("Hello"), class_="card", on_click=handler)
```

Children are positional arguments and props are keyword arguments.

Prop name mapping (Python keyword to HTML attribute):

- `class_` → `class` (the canonical reserved-word workaround).
- `html_for` → `for` (Python reserved word).
- All other kwargs pass through unchanged.

Each helper exported here (e.g. `div`, `p`, `button`, `input_`) is a
thin wrapper that returns a [`VNode`][wybthon.VNode]. Two element
names collide with Python builtins, so they are exposed with a trailing
underscore: `main_` and `input_`.

See Also:
    - [`h`][wybthon.h] — the underlying hyperscript constructor.
    - [`Fragment`][wybthon.Fragment] — wrap a list of children with no
      DOM parent.
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

    Maps the reserved-word workarounds `class_` to `class` and
    `html_for` to `for`. All other keys pass through unchanged.

    Args:
        kwargs: Keyword arguments captured from an element helper.

    Returns:
        A new props dictionary suitable for passing to
        [`h`][wybthon.h].
    """
    props: dict = {}
    for key, value in kwargs.items():
        if key == "class_":
            props["class"] = value
        elif key == "html_for":
            props["for"] = value
        else:
            props[key] = value
    return props


def _el(tag: str) -> Callable[..., VNode]:
    """Create a helper function for the given HTML tag name.

    Args:
        tag: HTML tag name (e.g. `"div"`, `"section"`).

    Returns:
        A callable `element_fn(*children, **props) -> VNode` that
        constructs a `VNode` for the requested tag.
    """

    def element_fn(*children: Any, **props: Any) -> VNode:
        """Create a `<{tag}>` element. Children are positional, props are keyword."""
        return h(tag, _process_props(props), *children)

    element_fn.__name__ = tag
    element_fn.__qualname__ = tag
    element_fn.__doc__ = f"Create a `<{tag}>` element. Children are positional args, props are keyword args."
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
