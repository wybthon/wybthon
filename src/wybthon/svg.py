"""SVG element helpers.

The same calling convention as [`wybthon.html`][wybthon.html]: children
are positional, props are keyword arguments, and underscores in prop
names become hyphens (`stroke_width="2"` renders `stroke-width="2"`).
Attribute names that are camelCase in SVG (`viewBox`, `preserveAspectRatio`)
are passed through `**{"viewBox": ...}` or the `view_box` alias below.

The reconciler infers the SVG namespace from the `svg` root, so these
helpers work inside an HTML tree without extra configuration:

```python
from wybthon.svg import svg, circle

svg(circle(cx=50, cy=50, r=40, fill=lambda: color()), viewBox="0 0 100 100")
```

Names that clash with HTML helpers (`a`, `title`, `text`) live here
under their SVG meaning; import from this module explicitly.
"""

from __future__ import annotations

from typing import Any

from .html import element
from .vnode import VNode, h

__all__ = [
    "svg",
    "g",
    "defs",
    "symbol",
    "use",
    "path",
    "circle",
    "ellipse",
    "line",
    "polyline",
    "polygon",
    "rect",
    "text",
    "tspan",
    "image",
    "clipPath",
    "mask",
    "pattern",
    "marker",
    "linearGradient",
    "radialGradient",
    "stop",
    "filter_",
    "foreignObject",
    "title",
    "desc",
    "a",
]

# SVG attributes whose canonical spelling is camelCase; the Pythonic
# snake_case spelling is translated here.
_CAMEL_ATTRS = {
    "view_box": "viewBox",
    "preserve_aspect_ratio": "preserveAspectRatio",
    "gradient_units": "gradientUnits",
    "gradient_transform": "gradientTransform",
    "pattern_units": "patternUnits",
    "pattern_transform": "patternTransform",
    "marker_width": "markerWidth",
    "marker_height": "markerHeight",
    "marker_units": "markerUnits",
    "ref_x": "refX",
    "ref_y": "refY",
    "clip_path_units": "clipPathUnits",
    "mask_units": "maskUnits",
    "text_length": "textLength",
    "length_adjust": "lengthAdjust",
    "spread_method": "spreadMethod",
    "stdDeviation": "stdDeviation",
    "std_deviation": "stdDeviation",
    "base_frequency": "baseFrequency",
    "num_octaves": "numOctaves",
}


def _svg_props(kwargs: dict[str, Any]) -> dict[str, Any]:
    if not kwargs:
        return kwargs
    props: dict[str, Any] = {}
    for key, value in kwargs.items():
        if key == "class_":
            props["class"] = value
        else:
            props[_CAMEL_ATTRS.get(key, key)] = value
    return props


def _svg_el(tag: str) -> Any:
    def element_fn(*children: Any, **props: Any) -> VNode:
        return h(tag, _svg_props(props), *children)

    element_fn.__name__ = tag
    element_fn.__qualname__ = tag
    element_fn.__doc__ = f"Create an SVG `<{tag}>` element. Children are positional args, props are keyword args."
    return element_fn


svg = _svg_el("svg")
g = _svg_el("g")
defs = _svg_el("defs")
symbol = _svg_el("symbol")
use = _svg_el("use")
path = _svg_el("path")
circle = _svg_el("circle")
ellipse = _svg_el("ellipse")
line = _svg_el("line")
polyline = _svg_el("polyline")
polygon = _svg_el("polygon")
rect = _svg_el("rect")
text = _svg_el("text")
tspan = _svg_el("tspan")
image = _svg_el("image")
clipPath = _svg_el("clipPath")
mask = _svg_el("mask")
pattern = _svg_el("pattern")
marker = _svg_el("marker")
linearGradient = _svg_el("linearGradient")
radialGradient = _svg_el("radialGradient")
stop = _svg_el("stop")
filter_ = _svg_el("filter")
foreignObject = _svg_el("foreignObject")
title = _svg_el("title")
desc = _svg_el("desc")
a = _svg_el("a")

# Re-exported so ``from wybthon.svg import element`` also works for
# less common SVG tags (``element("feGaussianBlur")``).
element = element
