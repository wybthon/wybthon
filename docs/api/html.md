### wybthon.html

::: wybthon.html

#### What's in this module

One helper per common HTML element, each calling
[`h()`][wybthon.h] with children as positional arguments and props as
keyword arguments, plus [`element()`][wybthon.element] for tags without a
built-in helper. Every helper is also re-exported from `wybthon`.

| Group | Helpers |
| --- | --- |
| Layout | `div`, `span`, `section`, `article`, `aside`, `header`, `footer`, `main_`, `nav` |
| Headings and text | `h1` to `h6`, `p`, `a`, `strong`, `em`, `small`, `code`, `pre`, `br`, `hr`, `blockquote`, `mark`, `time` |
| Lists and tables | `ul`, `ol`, `li`, `table`, `thead`, `tbody`, `tfoot`, `tr`, `th`, `td`, `caption`, `colgroup`, `col` |
| Forms | `form`, `input_`, `textarea`, `select`, `option`, `optgroup`, `button`, `label`, `fieldset`, `legend`, `progress`, `meter` |
| Media and interactive | `img`, `video`, `audio`, `source`, `canvas`, `picture`, `track`, `details`, `summary`, `dialog`, `figure`, `figcaption` |
| Factory | [`element(tag)`][wybthon.element] returns a helper for any tag name (custom elements included). |

#### Naming rules

- `class_` becomes `class` and `html_for` becomes `for` (Python reserved words).
- Other underscores become hyphens: `aria_label`, `data_testid`, `stroke_width`.
- `input_` and `main_` carry a trailing underscore because `input` and `main` collide with Python builtins.
- Event handlers keep the `on_` prefix: `on_click`, `on_input`.
- `True` sets a boolean attribute (`disabled=True`); `False` or `None` omits it. See [props](props.md) for the full value rules.

```python
from wybthon import a, button, div, element, input_, label, main_, p

my_widget = element("my-widget")

view = main_(
    div(
        label("Name", html_for="name"),
        input_(id="name", type="text", placeholder="Ada", required=True, aria_label="Your name"),
        button("Save", type="submit", disabled=lambda: not valid()),
        class_="form-row",
        data_testid="name-row",
    ),
    p("Read the ", a("docs", href="https://wybthon.com/"), "."),
    my_widget("custom element content", size="large"),
)
```

#### SVG

SVG elements live in [`wybthon.svg`](svg.md) with the same calling
convention. The reconciler infers the SVG namespace from the `svg` root,
so an SVG subtree drops straight into an HTML tree. Names that clash
with HTML helpers (`a`, `title`, `text`) carry their SVG meaning there.

#### See also

- [`h`][wybthon.h] and [`Fragment`][wybthon.Fragment] in [vnode](vnode.md)
- [Props](props.md): attribute, property, class, and style semantics
- [Events](events.md): `on_*` handler props
- [Concepts: Virtual DOM](../concepts/vdom.md)
