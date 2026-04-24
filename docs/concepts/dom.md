# DOM interop

[`Element`][wybthon.Element] is Wybthon's thin wrapper around browser DOM nodes. It provides ergonomic helpers for attributes, classes, styles, events, and queries while still giving you the raw `element` for any escape hatches you need.

```python
from wybthon.dom import Element

root = Element("#app", existing=True)
div = Element("div")
div.set_text("Hello")
div.append_to(root)
```

You rarely need to instantiate `Element` directly when authoring components; the renderer creates and manages elements for you. Use it when you need to bridge to imperative DOM APIs (focus management, scrolling, third-party widgets) or when you receive a node back from a `ref`.

## Refs: holding onto an element

A [`Ref`][wybthon.Ref] is a small mutable container that the renderer fills with the mounted [`Element`][wybthon.Element]. Pass `ref=` to any host element and read `ref.current` inside [`on_mount`][wybthon.on_mount] to interact with the underlying node.

```python
from wybthon import Ref, component, on_mount
from wybthon.html import input_, div


@component
def AutoFocusInput():
    ref = Ref()

    @on_mount
    def _focus():
        if ref.current is not None:
            ref.current.element.focus()

    return div(input_(type="text", placeholder="Focus me", ref=ref))
```

Because the ref is populated after mount, never read `ref.current` from the component body during initial render. Use [`on_mount`][wybthon.on_mount], an effect, or an event handler instead.

## How the VDOM uses `Element`

Every host VNode the reconciler renders is backed by an `Element`. When the reconciler creates a node, it:

1. Calls `Element(tag)` (or wraps an existing node).
2. Applies initial props through `apply_initial_props`, which delegates to `Element.set_attr`, `Element.set_style`, `Element.add_class`, and the event-delegation helpers.
3. Recursively mounts children and `appendChild`s them via `Element.append_to`.

On update, the reconciler diffs old vs. new props through `apply_props` and either patches the existing element in place or unmounts it (calling `Element.remove`) when the type changes. Because the wrapper holds the underlying node directly, even imperative effects you trigger from a ref stay in sync with the framework's bookkeeping.

## Styles and dataset via VDOM

- Use the `style` prop with a dict of camelCase keys; the VDOM converts to kebab-case and calls `style.setProperty`. Missing keys on update are removed. Passing `None` clears previous styles.
- Use the `dataset` prop with a dict; entries render as `data-*` attributes. Missing keys on update are removed. Passing `None` clears previous dataset entries.

## Next steps

- Read [Events](events.md) for how delegated handlers attach to elements.
- See [Forms](forms.md) for accessible patterns built on top of `Element`.
