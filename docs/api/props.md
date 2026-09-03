### wybthon.props

::: wybthon.props

#### What's in this module

`props` translates the keyword arguments you pass to element helpers
into batched DOM ops: attributes, DOM properties, class and style
objects, datasets, delegated events, refs, and per-prop reactive
bindings. Application code never imports it; this page documents the
rules it applies to every element prop.

#### Normalization rules

| Prop value or name | What the applier does |
| --- | --- |
| `class_`, `html_for`, `for_` | Written as the `class` and `for` attributes. |
| Any other name with underscores | Underscores become hyphens: `aria_label`, `data_testid`, `stroke_width`. |
| `True` | Sets the attribute. Known boolean attributes (`disabled`, `checked`, `hidden`, `required`, `readonly`, `selected`, `multiple`, `open`, `autofocus`, ...) get `""`; anything else gets `"true"`. |
| `False` or `None` | Removes the attribute. |
| `value`, `checked`, `inner_html` / `innerHTML` | Set as DOM properties, not attributes. `value` and `checked` are always re-asserted on patch so controlled inputs win over user edits. |
| `class` as a `str`, `list`, or `dict` | Lists join truthy entries; dicts include keys whose values are truthy. |
| `style` as a `dict` or `str` | Dict keys may be snake_case or camelCase and are converted to kebab-case; `None` or `False` removes a declaration; a string sets the `style` attribute. |
| `dataset={...}` | Each key becomes a `data-*` attribute. |
| `on_click`, `on_input`, `onClick`, ... | Registered with root-scoped event delegation; see [events](events.md). |
| `ref` | A [`Ref`][wybthon.Ref], a callback `ref(el)`, or a list of either; assigned an `Element` on mount, `Ref.current` reset to `None` on unmount. |
| `key`, `children` | Never written to the DOM. |

Any prop value that is an accessor or zero-arg function, or a `class` or
`style` dict containing one, becomes a **reactive binding**: its own
render effect re-applies just that prop when its reads change. A
binding that raises `NotReadyError` keeps the current DOM value; other
exceptions route to the nearest [`Errored`][wybthon.Errored] boundary.

```python
from wybthon import Ref, button, create_signal, input_

active, set_active = create_signal(False)
name, set_name = create_signal("")
field = Ref()

button(
    "Toggle",
    class_={"btn": True, "btn-active": active},          # reactive dict entry
    style={"font_weight": lambda: "bold" if active() else "normal"},
    aria_pressed=active,                                  # renders "true" / removed
    disabled=lambda: name() == "",                        # boolean attribute
    on_click=lambda e: set_active(lambda v: not v),
)
input_(value=name, on_input=lambda e: set_name(e.target.value), ref=field)
```

#### See also

- [HTML helpers](html.md) and [SVG helpers](svg.md)
- [Events](events.md): delegated handler props
- [DOM](dom.md): `Element` and `Ref`
- [Concepts: DOM interop](../concepts/dom.md)
