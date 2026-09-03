### wybthon.svg

::: wybthon.svg

#### What's in this module

SVG element helpers with the same calling convention as
[`wybthon.html`](html.md): children are positional, props are keyword
arguments, and underscores in prop names become hyphens
(`stroke_width="2"` renders `stroke-width="2"`). The reconciler infers
the SVG namespace from the `svg` root and creates the subtree with
`createElementNS`, so these helpers work inside an HTML tree with no
extra configuration. They aren't re-exported from `wybthon`; import them
from `wybthon.svg`.

| Group | Helpers |
| --- | --- |
| Containers | `svg`, `g`, `defs`, `symbol`, `use`, `a`, `foreignObject` |
| Shapes | `path`, `circle`, `ellipse`, `line`, `polyline`, `polygon`, `rect` |
| Text and metadata | `text`, `tspan`, `title`, `desc`, `image` |
| Paint and effects | `linearGradient`, `radialGradient`, `stop`, `pattern`, `marker`, `mask`, `clipPath`, `filter_` |
| Factory | `element(tag)` (re-exported from `wybthon.html`) for tags without a helper, such as `element("feGaussianBlur")`. |

#### Naming rules

- CamelCase attributes can be written as-is (`viewBox="0 0 100 100"`) or
  with a snake_case alias that's translated for you: `view_box`,
  `preserve_aspect_ratio`, `gradient_units`, `gradient_transform`,
  `pattern_units`, `marker_width`, `marker_height`, `ref_x`, `ref_y`,
  `text_length`, `std_deviation`, and similar.
- `class_` becomes `class`; any other underscore becomes a hyphen
  (`stroke_linecap`, `fill_opacity`).
- `filter_` carries a trailing underscore because `filter` is a Python
  builtin. `a`, `title`, and `text` shadow the HTML helpers of the same
  name, so import them from `wybthon.svg` explicitly.

```python
from wybthon import create_signal, div
from wybthon.svg import circle, svg, text

color, set_color = create_signal("tomato")

chart = div(
    svg(
        circle(cx=50, cy=50, r=40, fill=color, stroke="black", stroke_width=2),
        text("hi", x=50, y=55, text_anchor="middle"),
        view_box="0 0 100 100",
        width=200,
        height=200,
    ),
    class_="chart",
)
```

Reactive values (accessors or zero-arg functions) work as SVG attribute
values exactly as they do for HTML props.

#### See also

- [HTML helpers](html.md)
- [Props](props.md): attribute and reactive binding semantics
- [Concepts: Virtual DOM](../concepts/vdom.md)
