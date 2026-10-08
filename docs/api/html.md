### wybthon.html

::: wybthon.html

#### What's in this module

One helper per HTML element, each building a [`VNode`][wybthon.VNode]
with children as positional arguments and props as keyword arguments,
plus [`element()`][wybthon.element] for tags without a built-in helper.
Every helper is also re-exported from `wybthon`. Children can also be
passed with item syntax, `div(class_="card")[h2("Title"), p("Body")]`,
which keeps long prop lists ahead of the content.

| Group | Helpers |
| --- | --- |
| Layout | `div`, `span`, `section`, `article`, `aside`, `header`, `footer`, `main_`, `nav`, `address`, `hgroup`, `search` |
| Headings | `h1` to `h6` |
| Text | `p`, `a`, `strong`, `em`, `b`, `i`, `u`, `s`, `small`, `code`, `kbd`, `samp`, `var`, `pre`, `br`, `wbr`, `hr`, `blockquote`, `q`, `cite`, `abbr`, `dfn`, `mark`, `time`, `data`, `sub`, `sup`, `del_`, `ins`, `bdi`, `bdo`, `ruby`, `rt`, `rp` |
| Lists | `ul`, `ol`, `li`, `dl`, `dt`, `dd`, `menu` |
| Tables | `table`, `thead`, `tbody`, `tfoot`, `tr`, `th`, `td`, `caption`, `colgroup`, `col` |
| Forms | `form`, `input_`, `textarea`, `select`, `option`, `optgroup`, `button`, `label`, `fieldset`, `legend`, `output`, `progress`, `meter`, `datalist` |
| Media and embedded content | `img`, `video`, `audio`, `source`, `canvas`, `picture`, `track`, `iframe`, `embed`, `object_`, `map_`, `area` |
| Interactive | `details`, `summary`, `dialog` |
| Semantic and templating | `figure`, `figcaption`, `template`, `slot` |
| Factory | [`element(tag)`][wybthon.element] returns a helper for any tag name (custom elements included). |

#### Naming rules

The helpers store props exactly as written
(`div(class_="x").props == {"class_": "x"}`); the prop applier maps the
names when it writes attributes:

- `class_` becomes `class`, and `html_for` (or `for_`) becomes `for`.
- Other underscores become hyphens: `aria_label`, `data_testid`, `stroke_width`.
- `input_`, `main_`, `del_`, `object_`, and `map_` carry a trailing underscore because their names collide with Python builtins or keywords.
- Event handlers keep the `on_` prefix: `on_click`, `on_input`.

#### Prop values

| Prop value or name | What the applier does |
| --- | --- |
| `True` | Sets the attribute. Known boolean attributes (`disabled`, `checked`, `hidden`, `required`, `readonly`, `selected`, `multiple`, `open`, `autofocus`, ...) get `""`; anything else gets `"true"`. |
| `False` or `None` | Removes the attribute. |
| `value`, `checked`, `selected_values`, `inner_html` / `innerHTML` | Set as DOM properties, not attributes. `value` and `checked` are always re-asserted on patch so controlled inputs win over user edits. |
| `class_` as a `str`, `list`, or `dict` | Lists join truthy entries; dicts include keys whose values are truthy. |
| `style` as a `dict` or `str` | Dict keys may be snake_case or camelCase and are converted to kebab-case; `None` or `False` removes a declaration; a string sets the `style` attribute. |
| `dataset={...}` | Each key becomes a `data-*` attribute. |
| `on_click`, `on_input`, `onClick`, ... | Registered with root-scoped event delegation; see [events](events.md). |
| `ref` | A [`Ref`][wybthon.Ref], a callback `ref(el)`, or a list of either; assigned an `Element` on mount, `Ref.current` reset to `None` on unmount. |
| `key`, `children` | Never written to the DOM. |

Any prop value that's an accessor, a zero-arg function, or a template
string with a reactive interpolation (`class_=t"btn btn-{kind}"`), or a
`class_` or `style` dict containing one, becomes a **reactive binding**:
its own render effect re-applies just that prop when its reads change.
A template string with no reactive interpolations is static. A binding
that raises `NotReadyError` keeps the current DOM value; other
exceptions route to the nearest [`Errored`][wybthon.Errored] boundary.

```python
from wybthon import Ref, a, button, create_signal, div, element, input_, label, main_, p

name, set_name = create_signal("")
active, set_active = create_signal(False)
field = Ref()
my_widget = element("my-widget")

view = main_(
    div(class_="form-row", data_testid="name-row")[
        label("Name", html_for="name"),
        input_(id="name", type="text", value=name, on_input=lambda e: set_name(e.target.value), ref=field),
        button(
            "Save",
            type="submit",
            class_={"btn": True, "btn-active": active},  # reactive dict entry
            aria_pressed=active,  # renders "true" or is removed
            disabled=lambda: name() == "",  # boolean attribute
            on_click=lambda: set_active(lambda v: not v),
        ),
    ],
    p(t"Hello, {name}! Read the ", a("docs", href="https://wybthon.com/"), "."),
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
- [Events](events.md): `on_*` handler props
- [DOM](dom.md): `Element` and `Ref`
- [Concepts: Virtual DOM](../concepts/vdom.md)
- [Concepts: DOM interop](../concepts/dom.md)
