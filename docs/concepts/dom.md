# DOM interop

[`Element`][wybthon.Element] is Wybthon's thin wrapper around browser
DOM nodes. It provides helpers for attributes, classes, styles, and
queries while still giving you the raw `element` for any escape hatch
you need. For events, use the delegated `on_*` props (see
[Events](events.md)); for non-bubbling event types, attach a native
listener via `ref.current.element.addEventListener` with a Pyodide
proxy.

```python
from wybthon import Element

root = Element("#app", existing=True)
box = Element("div")
box.set_text("Hello")
box.append_to(root)
```

You rarely instantiate `Element` yourself when authoring components;
the renderer creates and manages nodes for you. Reach for it when you
need to bridge to imperative DOM APIs (focus management, scrolling,
measuring, third-party widgets) or when you receive a node back from a
`ref` or an event.

## Refs: holding onto an element

A [`Ref`][wybthon.Ref] is a small mutable container that the renderer
fills with the mounted `Element`. Pass `ref=` to any host element and
read `ref.current` after mount:

```python
from wybthon import Ref, component, on_settled
from wybthon.html import div, input_


@component
def AutoFocusInput():
    ref = Ref()

    def focus():
        if ref.current is not None:
            ref.current.element.focus()

    on_settled(focus)
    return div(input_(type="text", placeholder="Focus me", ref=ref))
```

Refs are assigned while the element mounts and reset to `None` when it
unmounts. Read them in [`on_settled`][wybthon.on_settled] (which runs
after the first commit), in an effect, or in an event handler, never
at the top of the component body during initial render.

### Ref shapes

The `ref` prop accepts three shapes:

- A `Ref` object: `ref.current` is set on mount and cleared on unmount.
- A callable: `ref(element)` is called once on mount. It isn't called again on unmount, so pair it with [`on_cleanup`][wybthon.on_cleanup] if you need teardown.
- A list or tuple mixing both: every entry is assigned. This is how a component forwards a parent's ref while keeping one of its own:

```python
from wybthon import Prop, Ref, component, on_settled, prop
from wybthon.html import input_


@component
def FancyInput(ref: Prop[Ref | None] = prop(None)):
    local = Ref()
    on_settled(lambda: local.current.element.focus())
    return input_(type="text", ref=[local, ref.peek()])
```

Refs pass through components like any other prop; there's no special
forwarding API. A `None` entry in the list is ignored.

## Ownership and disposal order

Refs follow the ownership tree. A component's `ref.current` is set from
the first commit until the component unmounts. During unmount the
component's own cleanups run first, then its host nodes' refs are
cleared, then the freed node ids are released to the kernel. So an
`on_cleanup` registered in the component body can still reach
`ref.current` to tear down a native listener or a third-party widget.
Materializing `ref.current.element` at that point commits the pending
remove op, so the node may already be detached from the document; use
it for teardown, not for measurements. Cleanups that run later (for
example ones registered by an ancestor) see `ref.current is None`, so
guard for it. See [Lifecycle and ownership](lifecycle.md).

## How the renderer relates to `Element`

The renderer itself never touches raw DOM nodes or `Element` wrappers.
Every host VNode is identified by an integer node id, and all mutations
(create, insert, set-attr, listen) are emitted as compact operations
into a command buffer that a small JavaScript kernel applies in one
bridge crossing per commit. See [Virtual DOM](vdom.md).

`Element` sits on top of that system as the escape hatch for imperative
work:

- An `Element` can be backed by a raw DOM node (when you construct one yourself, or wrap one with `Element(node=...)`) or by a kernel node id (what the renderer hands out through `ref=` and `evt.current_target`).
- Id-backed elements materialize the raw node lazily: the first `element` access commits any pending batched ops, then fetches the node from the kernel's registry, so what you see always reflects every queued mutation.
- `node_id` goes the other way: it registers a raw-node-backed element with the kernel so the renderer can target it. [`render`][wybthon.render] uses this when you pass an `Element` container.
- Query helpers (`Element.query`, `Element.query_all`, `find`, `find_all`) also commit pending ops first, so nodes created earlier in the same update are visible.

Because commits happen automatically at these boundaries, imperative
work through a ref stays in sync with the framework's bookkeeping.

!!! warning "Don't fight the renderer"
    Attributes, classes, and children that the renderer owns should be
    driven by reactive bindings, not by `Element` calls. The next
    reconciliation only patches what changed on the VNode, so it won't
    notice manual edits and may leave them in place, or overwrite them
    unexpectedly. Use `Element` for things the renderer doesn't manage:
    focus, selection, scroll position, measurements, and third-party
    widgets that own their subtree.

## Element helpers

The wrapper mirrors familiar DOM names:

| Helper | Purpose |
| --- | --- |
| `element` | The raw JS node (materialized lazily). |
| `value`, `checked`, `files` | Form-control state, readable and (for `value`, `checked`) writable. |
| `set_text`, `set_html`, `load_html` | Replace content. `set_html` bypasses diffing and doesn't sanitize. |
| `set_attr`, `get_attr`, `remove_attr` | Attribute access. |
| `set_style(dict_or_kwargs)` | Calls `style.setProperty` per entry. |
| `add_class`, `remove_class`, `toggle_class`, `has_class` | `classList` shortcuts. |
| `append`, `append_to`, `remove` | Tree manipulation for nodes you own. |
| `Element.query`, `Element.query_all`, `find`, `find_all` | Selector queries (commit pending ops first). |
| `attach_ref(ref)` | Store this element on `ref.current`. |

## Styles and dataset via the VDOM

You usually don't need `Element` for styling:

- The `style` prop takes a dict with camelCase or snake_case keys (`background_color`, `fontSize`); the renderer converts to kebab-case and emits a single style op. Keys missing on update are removed, and passing `None` clears earlier styles. Values may be accessors, and a raw style string is accepted too.
- The `dataset` prop takes a dict; entries render as `data-*` attributes and missing keys on update are removed. Keyword props like `data_testid="x"` also work.
- `class_` accepts a string, a list of strings, a `{name: truthy_or_accessor}` dict, or an accessor returning any of those.

## Rendering into an existing node

[`render(vnode, container)`][wybthon.render] accepts an `Element`
container and returns a [`Root`][wybthon.Root]. Call `root.dispose()` to
unmount, run every cleanup, and clear the container's kernel bookkeeping:

```python
from wybthon import Element, render
from wybthon.html import h1

root = render(h1("Hello"), Element("#app", existing=True))
root.dispose()
```

## Next steps

- Read [Events](events.md) for how delegated handlers attach to elements.
- See [Forms](forms.md) for accessible patterns built on top of `Element`.
- Browse the [`dom`](../api/dom.md) API reference.
