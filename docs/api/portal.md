### wybthon.portal

::: wybthon.portal

#### What's in this module

[`create_portal`][wybthon.create_portal] renders its children into a
different DOM container while keeping them logically inside the
component tree (so context, ownership, and event delegation still work).

This is the right tool for modals, tooltips, popovers, and toast
notifications that need to escape the visual layout of their parent.

#### Usage

```python
from wybthon import component, create_portal, create_signal
from wybthon.html import button, div, p


@component
def Modal():
    open_, set_open = create_signal(False)

    def toggle(_e):
        set_open(not open_())

    return div(
        button("Open", on_click=toggle),
        Show(
            when=open_,
            children=lambda: create_portal(
                mount=document.body,
                children=lambda: div(
                    p("I'm in document.body!"),
                    button("Close", on_click=toggle),
                    class_="modal",
                ),
            ),
        ),
    )
```

- `mount` accepts a DOM element or a CSS selector string.
- The portal cleans up its content when its owner unmounts.
- Events bubble through the React-like component tree, *not* the DOM
  tree — handy for keeping modal logic close to the trigger.

#### See also

- [Concepts → DOM Interop](../concepts/dom.md)
- [Concepts → Components](../concepts/components.md)
