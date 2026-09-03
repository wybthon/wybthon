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
| [`VNode`][wybthon.VNode] | Element, text, component, fragment, or hole node; `tag`, `props`, `children`, `key`. |
| [`h`][wybthon.h] | Hyperscript constructor: `h(tag, props, *children)`; components get children as the `children` prop. |
| [`Fragment`][wybthon.Fragment] | Group children with no wrapper element. |
| [`hole`][wybthon.hole] | Explicit reactive hole, optionally with a `key`. |

Holes are created implicitly: any accessor or zero-arg callable in a
child position becomes one. Reach for `hole()` when you need a stable
`key` or want the hole visually explicit.

```python
from wybthon import Fragment, create_signal, h, hole

name, set_name = create_signal("Ada")

view = h(
    "section",
    {"class": "card"},
    h("h1", {}, "Hello, ", name),                 # implicit hole
    hole(lambda: f"{len(name())} letters"),       # explicit hole
    Fragment(h("p", {}, "Body 1"), h("p", {}, "Body 2")),
)
```

The [`wybthon.html`](html.md) helpers wrap `h()` with keyword props, so
most application code writes `section(h1("Hello, ", name), class_="card")`
instead.

#### See also

- [HTML helpers](html.md) and [SVG helpers](svg.md)
- [`is_accessor`][wybthon.is_accessor]: the rule that decides what becomes a hole
- [Reconciler](reconciler.md): how VNodes mount and patch
- [Concepts: Virtual DOM](../concepts/vdom.md)
