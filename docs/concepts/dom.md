# DOM interop

[`Element`][wybthon.Element] is Wybthon's thin wrapper around browser DOM nodes. It provides ergonomic helpers for attributes, classes, styles, and queries while still giving you the raw `element` for any escape hatches you need. For events, use the delegated `on_*` props (see [Events](events.md)); for non-bubbling event types, attach a native listener via `ref.current.element.addEventListener` with a Pyodide proxy.

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

## How the renderer relates to `Element`

The renderer itself never touches raw DOM nodes or `Element` wrappers. Every host VNode is identified by an integer node id, and all mutations (create, insert, set-attr, listen) are emitted as compact operations into a command buffer that a small JavaScript kernel applies in one bridge crossing per commit.

`Element` sits *on top* of that system as the escape hatch for imperative work:

- An `Element` can be backed by a raw DOM node (when you construct one yourself) or by a kernel node id (what the renderer hands out through `ref=` and `evt.current_target`).
- Id-backed elements materialize the raw node lazily: the first `element` access commits any pending batched ops, then fetches the node from the kernel's registry, so what you see always reflects every queued mutation.
- Query helpers (`Element.query`, `find`, ...) also commit pending ops first, so nodes created earlier in the same update are visible.

Because commits happen automatically at these boundaries, imperative work through a ref stays in sync with the framework's bookkeeping.

## Styles and dataset via VDOM

- Use the `style` prop with a dict of camelCase keys; the VDOM converts to kebab-case and calls `style.setProperty`. Missing keys on update are removed. Passing `None` clears previous styles.
- Use the `dataset` prop with a dict; entries render as `data-*` attributes. Missing keys on update are removed. Passing `None` clears previous dataset entries.

## Next steps

- Read [Events](events.md) for how delegated handlers attach to elements.
- See [Forms](forms.md) for accessible patterns built on top of `Element`.
