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

Children may also be t-strings: `p(t"Count: {count}")` updates as one
reactive text node.

Each helper returns a [`VNode`][wybthon.VNode]. Element names that
collide with Python builtins or keywords are exposed with a trailing
underscore: `main_`, `input_`, `del_`, and `object_`. SVG elements live
in [`wybthon.svg`][wybthon.svg].

See Also:
    - [`h`][wybthon.h]: the underlying hyperscript constructor.
    - [`Fragment`][wybthon.Fragment]: group children with no DOM parent.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .vnode import Fragment, VNode, flatten_children

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
    "address",
    "hgroup",
    "search",
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
    "b",
    "i",
    "u",
    "s",
    "small",
    "code",
    "kbd",
    "samp",
    "var",
    "pre",
    "br",
    "wbr",
    "hr",
    "blockquote",
    "q",
    "cite",
    "abbr",
    "dfn",
    "mark",
    "time",
    "data",
    "sub",
    "sup",
    "del_",
    "ins",
    "bdi",
    "bdo",
    "ruby",
    "rt",
    "rp",
    # Lists
    "ul",
    "ol",
    "li",
    "dl",
    "dt",
    "dd",
    "menu",
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
    "output",
    "progress",
    "meter",
    "datalist",
    # Media and embedded content
    "img",
    "video",
    "audio",
    "source",
    "canvas",
    "picture",
    "track",
    "iframe",
    "embed",
    "object_",
    "map_",
    "area",
    # Interactive
    "details",
    "summary",
    "dialog",
    # Semantic and templating
    "figure",
    "figcaption",
    "template",
    "slot",
]


def element(tag: str) -> Callable[..., VNode]:
    """Create a helper `fn(*children, **props) -> VNode` for any tag name.

    Use it for custom elements or tags without a built-in helper:

    ```python
    my_widget = element("my-widget")
    my_widget("content", size="large")
    ```
    """

    def element_fn(*children: Any, **props: Any) -> VNode:
        if not children:
            kids: list[Any] = []
        elif len(children) == 1 and type(children[0]) in (VNode, str):
            kids = [children[0]]
        else:
            kids = flatten_children(children)
        return VNode(tag, props, kids, props.get("key") if props else None)

    element_fn.__name__ = tag.replace("-", "_")
    element_fn.__qualname__ = element_fn.__name__
    element_fn.__doc__ = f"Create a `<{tag}>` element. Children are positional args, props are keyword args."
    return element_fn


# Layout
div = element("div")
span = element("span")
section = element("section")
article = element("article")
aside = element("aside")
header = element("header")
footer = element("footer")
main_ = element("main")
nav = element("nav")
address = element("address")
hgroup = element("hgroup")
search = element("search")

# Headings
h1 = element("h1")
h2 = element("h2")
h3 = element("h3")
h4 = element("h4")
h5 = element("h5")
h6 = element("h6")

# Text
p = element("p")
a = element("a")
strong = element("strong")
em = element("em")
b = element("b")
i = element("i")
u = element("u")
s = element("s")
small = element("small")
code = element("code")
kbd = element("kbd")
samp = element("samp")
var = element("var")
pre = element("pre")
br = element("br")
wbr = element("wbr")
hr = element("hr")
blockquote = element("blockquote")
q = element("q")
cite = element("cite")
abbr = element("abbr")
dfn = element("dfn")
mark = element("mark")
time = element("time")
data = element("data")
sub = element("sub")
sup = element("sup")
del_ = element("del")
ins = element("ins")
bdi = element("bdi")
bdo = element("bdo")
ruby = element("ruby")
rt = element("rt")
rp = element("rp")

# Lists
ul = element("ul")
ol = element("ol")
li = element("li")
dl = element("dl")
dt = element("dt")
dd = element("dd")
menu = element("menu")

# Tables
table = element("table")
thead = element("thead")
tbody = element("tbody")
tfoot = element("tfoot")
tr = element("tr")
th = element("th")
td = element("td")
caption = element("caption")
colgroup = element("colgroup")
col = element("col")

# Forms
form = element("form")
input_ = element("input")
textarea = element("textarea")
select = element("select")
option = element("option")
optgroup = element("optgroup")
button = element("button")
label = element("label")
fieldset = element("fieldset")
legend = element("legend")
output = element("output")
progress = element("progress")
meter = element("meter")
datalist = element("datalist")

# Media and embedded content
img = element("img")
video = element("video")
audio = element("audio")
source = element("source")
canvas = element("canvas")
picture = element("picture")
track = element("track")
iframe = element("iframe")
embed = element("embed")
object_ = element("object")
map_ = element("map")
area = element("area")

# Interactive
details = element("details")
summary = element("summary")
dialog = element("dialog")

# Semantic and templating
figure = element("figure")
figcaption = element("figcaption")
template = element("template")
slot = element("slot")
