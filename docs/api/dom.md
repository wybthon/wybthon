### wybthon.dom

::: wybthon.dom

#### What's in this module

`dom` is the imperative escape hatch. The renderer refers to nodes by
integer id and batches every mutation through the kernel;
[`Element`][wybthon.Element] wraps a real node (or a kernel node id,
materialized on first access after committing pending ops) so you can
read a value, focus an input, or call a browser API directly.
[`Ref`][wybthon.Ref] is the container the renderer fills in when an
element with `ref=` mounts.

| Name | Description |
| --- | --- |
| [`Element`][wybthon.Element] | Thin wrapper over a DOM node: `.element` (raw node), `.node_id`, `.value`, `.checked`, `.files`, attribute, class, style, and query helpers. |
| [`Ref`][wybthon.Ref] | Holds `.current` (an `Element`) after mount; reset to `None` on unmount. |

Construct an `Element` four ways: `Element("div")` creates a node,
`Element("#app", existing=True)` queries one, `Element(node=raw)` wraps a
node from another API, and `Element(node_id=42)` wraps a kernel id
(what refs and event targets hand you).

```python
from wybthon import Prop, Ref, component, input_, on_settled, prop

@component
def FancyInput(ref: Prop[Ref | None] = prop(None)):
    local = Ref()

    def focus():
        local.current.element.focus()

    on_settled(focus)
    # Forward the parent's ref (if any) and keep a local one.
    return input_(type="text", ref=[local, ref.peek()])
```

Refs are assigned during mount, so read them in
[`on_settled`][wybthon.on_settled], an effect, or an event handler, not
at the top of the component body. The `ref=` prop also accepts a
callback `ref(el)`.

`Element.query(selector)`, `.find(selector)`, and `.element` commit
pending batched ops first, so nodes created earlier in the same update
are visible to the read.

#### See also

- [Props](props.md): the `ref=` prop and DOM property rules
- [Events](events.md): `DomEvent.target` and `current_target` are `Element`-backed
- [Concepts: DOM interop](../concepts/dom.md)
