### wybthon.portal

::: wybthon.portal

#### What's in this module

[`Portal`][wybthon.Portal] renders its children into a different DOM
container while keeping them inside the current reactive ownership
tree, so signals, context, cleanups, and error boundaries behave exactly
as they would for in-place children. It's the tool for modals,
tooltips, popovers, and toasts that must escape their parent's layout.

| Name | Description |
| --- | --- |
| [`Portal`][wybthon.Portal] | `Portal(children, *, mount="body")`; `children` is a VNode, a list, or a zero-arg callable (rendered as a hole); `mount` is an `Element`, a CSS selector, or a kernel node id. |

```python
from wybthon import Portal, Show, button, component, create_signal, div, p

@component
def Modal():
    is_open, set_open = create_signal(False)

    def toggle(e):
        set_open(lambda v: not v)

    return div(
        button("Open", on_click=toggle),
        Show(
            is_open,
            lambda: Portal(
                div(p("I'm in #modal-root"), button("Close", on_click=toggle), class_="modal"),
                mount="#modal-root",
            ),
        ),
    )
```

- Content is removed when the portal's owner is disposed (here, when
  `Show` flips back to falsy).
- The mount target becomes an event delegation root for as long as the
  portal is mounted, so `on_*` handlers inside it fire even when the
  target sits outside the container passed to [`render`][wybthon.render]
  (a `<body>`-level modal layer, for example).
- Context flows through the reactive tree, not the DOM tree, so
  `use_context` inside the portal sees the surrounding providers.

#### See also

- [DOM](dom.md): `Element` for resolving mount targets
- [Concepts: DOM interop](../concepts/dom.md)
- [Concepts: Components](../concepts/components.md)
