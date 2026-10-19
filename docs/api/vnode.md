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
- The [element helpers](elements.md) and `h()` build ordinary element
  VNodes.

Treat these special tags as internal: build nodes with `html`, the
helpers, and the flow functions rather than by tag name.

Holes are created implicitly: any accessor or zero-arg callable in a
child position becomes one, in a template or a helper. A t-string
passed as a helper child (`p(t"Hello, {name}")`) is a single hole for
the whole string. Reach for `hole()` when you need a stable `key` or
want the hole visually explicit.

`VNode[...]` sets children with item syntax and returns the node, so
`section(class_="card")[h1("Hello"), p("Body")]` equals
`section(h1("Hello"), p("Body"), class_="card")`. A component call
supports the same syntax for its `children` prop.

A subtree mounted from a compiled helper shape keeps its VNodes, but
only the root and its dynamic children get `el` assigned at mount;
static descendants receive node ids lazily, when the reconciler first
patches the subtree. Don't rely on `.el` of a static descendant.

`h()` is the lowest-level way to build a tree, useful when the tag
itself is computed:

```python
from wybthon import Fragment, create_signal, h, hole

name, set_name = create_signal("Ada")

view = h(
    "section",
    {"class": "card"},
    h("h1", {}, "Hello, ", name),  # implicit hole
    hole(lambda: f"{len(name())} letters", key="count"),  # explicit hole with a key
    h("p", {}, t"Name: {name}"),  # t-string hole
    Fragment(h("p", {}, "Body 1"), h("p", {}, "Body 2")),
)
```

The [`wybthon.elements`](elements.md) helpers wrap `h()` with keyword
props (`section(h1("Hello, ", name), class_="card")`), and most
application code writes a template instead:
`html(t'<section class="card"><h1>Hello, {name}</h1></section>')`.

#### See also

- [Templates](../concepts/templates.md), [element helpers](elements.md), and [SVG helpers](svg.md)
- [`is_accessor`][wybthon.is_accessor]: the rule that decides what becomes a hole
- [Reconciler](reconciler.md): how VNodes mount and patch
- [Concepts: Virtual DOM](../concepts/vdom.md)
