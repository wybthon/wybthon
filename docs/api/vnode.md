### wybthon.vnode

::: wybthon.vnode

#### What's in this module

`vnode` defines the [`VNode`][wybthon.VNode] data structure and the pure
helpers that build trees of them. It has no browser dependency, so
trees can be constructed and inspected anywhere CPython runs. A
**reactive hole** is a `_hole` VNode wrapping an accessor or zero-arg
function; the reconciler runs it in its own render effect and patches
only that region when its reads change.

| Name | Description |
| --- | --- |
| [`VNode`][wybthon.VNode] | Element, text, component, fragment, hole, template, or region node; `tag`, `props`, `children`, `key`. |
| [`h`][wybthon.h] | Hyperscript constructor: `h(tag, props, *children)`; components get children as the `children` prop. |
| [`Fragment`][wybthon.Fragment] | Group children with no wrapper element. |
| [`hole`][wybthon.hole] | Explicit reactive hole, optionally with a `key`. |

Most nodes are built for you:

- [`html`][wybthon.html] returns a `_tpl` node for a template with one
  root element: a reference to the compiled template plus the
  interpolated values, with no VNodes for the static markup. A template
  with several roots returns a fragment, and one with no elements
  returns text.
- `Show` and `Switch` return `_branch` nodes, and `For` and `Repeat` return
  `_list` nodes; the reconciler mounts these as native regions.
- `h()` builds ordinary element VNodes.

Treat these special tags as internal: build nodes with `html`, `h`,
and the flow functions rather than by tag name.

Holes are created implicitly: any accessor or zero-arg callable in a
child position becomes one, whether it's a getter the compiler made
from `{count() * 2}` in a template or a function passed to `h()`.
Reach for `hole()` when you need a stable `key` or want the hole
visually explicit.

#### Building nodes with `h()`

`h()` is the programmatic layer, the counterpart of Solid's `h`. Most
markup is a template; use `h()` when code builds the markup: generated
forms, recursive trees, or a tag computed at run time. Templates and
`h()` trees mix freely in either direction.

```python
from wybthon import Fragment, create_signal, h, hole, html

name, set_name = create_signal("Ada")
active, set_active = create_signal(False)


def field(label, kind):
    return h("label", {}, label, h("input", {"type": kind, "aria_label": label}))


view = h(
    "section",
    {"class_": {"card": True, "active": active}, "data_testid": "card"},
    h("h1", {}, "Hello, ", name),  # an accessor child is a hole
    hole(lambda: f"{len(name())} letters", key="count"),  # explicit hole with a key
    [field(label, kind) for label, kind in [("Email", "email"), ("Age", "number")]],
    Fragment(h("p", {}, "Body 1"), h("p", {}, "Body 2")),
    html(t"<p>A template inside: {name()}</p>"),
)
```

`h()` evaluates its arguments before Wybthon sees them, so the compiler
can't help here: pass an accessor (`name`) or a function
(`lambda: name().upper()`) wherever a value should stay live. A
t-string isn't markup outside `html()`; passing one to `h()` raises
`TypeError`.

`VNode[...]` sets children with item syntax and returns the node, so
`h("section", {"class": "card"})[h("h1", {}, "Hello")]` equals
`h("section", {"class": "card"}, h("h1", {}, "Hello"))`. A component
call supports the same syntax for its `children` prop.

#### Prop names and values

`h()` stores props as written, and the prop applier maps the names when
it writes attributes. Templates write HTML names (`class`, `for`,
`aria-label`, `onclick`); `h()` props and template spreads
(`<input {attrs}>`) accept both those and Python names:

- `class_` becomes `class`, and `html_for` (or `for_`) becomes `for`.
- Other underscores become hyphens: `aria_label`, `data_testid`, `stroke_width`.
- Event handlers use the `on_` prefix (`on_click`, `on_input`) or the
  camelCase form (`onClick`).

| Prop value or name | What the applier does |
| --- | --- |
| `True` | Sets the attribute. Known boolean attributes (`disabled`, `checked`, `hidden`, `required`, `readonly`, `selected`, `multiple`, `open`, `autofocus`, ...) get `""`; anything else gets `"true"`. |
| `False` or `None` | Removes the attribute. |
| `value`, `checked`, `selected_values`, `inner_html` / `innerHTML` | Set as DOM properties, not attributes. `value` and `checked` are always re-asserted on patch so controlled inputs win over user edits. |
| `class` as a `str`, `list`, or `dict` | Lists join truthy entries; dicts include keys whose values are truthy. |
| `style` as a `dict` or `str` | Dict keys may be snake_case or camelCase and are converted to kebab-case; `None` or `False` removes a declaration; a string sets the `style` attribute. |
| `dataset={...}` | Each key becomes a `data-*` attribute. |
| `on_click`, `onClick`, ... | Registered with root-scoped event delegation; see [events](events.md). |
| `ref` | A [`Ref`][wybthon.Ref], a callback `ref(el)`, or a list of either; assigned an `Element` on mount, `Ref.current` reset to `None` on unmount. |
| `key`, `children` | Never written to the DOM. |

A prop value that's an accessor or a zero-arg function, or a `class` or
`style` dict containing one, becomes a **reactive binding** that
re-applies just that prop when its reads change. A binding that raises
`NotReadyError` keeps the current DOM value; other exceptions route to
the nearest [`Errored`][wybthon.Errored] boundary. These rules are
shared with template attributes, where the compiler supplies the
getters.

The reconciler infers the SVG namespace from an `svg` root, so
`h("svg", {"viewBox": "0 0 10 10"}, h("circle", {"r": 4}))` and a
`<svg>` in a template both render SVG elements.

#### See also

- [Templates](../concepts/templates.md): the `html` template function, the primary way to write markup
- [Compiler](compiler.md): how templates get their getters
- [`is_accessor`][wybthon.is_accessor]: the rule that decides what becomes a hole
- [Reconciler](reconciler.md): how VNodes mount and patch
- [Events](events.md) and [DOM](dom.md): handler props, `Element`, and `Ref`
- [Concepts: Virtual DOM](../concepts/vdom.md)
