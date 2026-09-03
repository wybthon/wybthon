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

- `class_` becomes `class` and `html_for` becomes `for` (reserved words).
- Underscores become hyphens: `aria_label`, `data_testid`, `tabindex`
  stays as is. Event handlers keep the `on_` prefix (`on_click`).
- `True` sets a boolean attribute, `False` or `None` omits it.

Each helper returns a [`VNode`][wybthon.VNode]. Two element names
collide with Python builtins, so they're exposed with a trailing
underscore: `main_` and `input_`. SVG elements live in
[`wybthon.svg`][wybthon.svg].

See Also:
    - [`h`][wybthon.h]: the underlying hyperscript constructor.
    - [`Fragment`][wybthon.Fragment]: group children with no DOM parent.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .vnode import Fragment, VNode, h

__all__ = [
    "Fragment",
    "element",
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
    "mark",
    "time",
    # Lists
    "ul",
    "ol",
    "li",
    # Tables
    "table",
    "thead",
    "tbody",
    "tfoot",
    "tr",
    "th",
    "td",
    "caption",
    "colgroup",
    "col",
    # Forms
    "form",
    "input_",
    "textarea",
    "select",
    "option",
    "optgroup",
    "button",
    "label",
    "fieldset",
    "legend",
    "progress",
    "meter",
    # Media
    "img",
    "video",
    "audio",
    "source",
    "canvas",
    "picture",
    "track",
    # Interactive
    "details",
    "summary",
    "dialog",
    # Semantic
    "figure",
    "figcaption",
]


def _process_props(kwargs: dict[str, Any]) -> dict[str, Any]:
    """Map reserved-word workarounds (`class_`, `html_for`) to their attribute names.

    Other names are left alone; the prop applier converts underscores to
    hyphens when it writes attributes.
    """
    if "class_" in kwargs or "html_for" in kwargs:
        props: dict[str, Any] = {}
        for key, value in kwargs.items():
            if key == "class_":
                props["class"] = value
            elif key == "html_for":
                props["for"] = value
            else:
                props[key] = value
        return props
    return kwargs


def element(tag: str) -> Callable[..., VNode]:
    """Create a helper `fn(*children, **props) -> VNode` for any tag name.

    Use it for custom elements or tags without a built-in helper:

    ```python
    my_widget = element("my-widget")
    my_widget("content", size="large")
    ```
    """

    def element_fn(*children: Any, **props: Any) -> VNode:
        return h(tag, _process_props(props), *children)

    element_fn.__name__ = tag.replace("-", "_")
    element_fn.__qualname__ = element_fn.__name__
    element_fn.__doc__ = f"Create a `<{tag}>` element. Children are positional args, props are keyword args."
    return element_fn


_el = element


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
mark = _el("mark")
time = _el("time")

# Lists
ul = _el("ul")
ol = _el("ol")
li = _el("li")

# Tables
table = _el("table")
thead = _el("thead")
tbody = _el("tbody")
tfoot = _el("tfoot")
tr = _el("tr")
th = _el("th")
td = _el("td")
caption = _el("caption")
colgroup = _el("colgroup")
col = _el("col")

# Forms
form = _el("form")
input_ = _el("input")
textarea = _el("textarea")
select = _el("select")
option = _el("option")
optgroup = _el("optgroup")
button = _el("button")
label = _el("label")
fieldset = _el("fieldset")
legend = _el("legend")
progress = _el("progress")
meter = _el("meter")

# Media
img = _el("img")
video = _el("video")
audio = _el("audio")
source = _el("source")
canvas = _el("canvas")
picture = _el("picture")
track = _el("track")

# Interactive
details = _el("details")
summary = _el("summary")
dialog = _el("dialog")

# Semantic
figure = _el("figure")
figcaption = _el("figcaption")
