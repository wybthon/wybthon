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
from wybthon import Props, Ref, component, html, on_settled


class FancyInputProps(Props):
    ref: Ref | None = None  # plain field: the parent's Ref, passed through untouched


@component
def FancyInput(props: FancyInputProps):
    local = Ref()

    def focus():
        local.current.element.focus()

    on_settled(focus)
    # Forward the parent's ref (if any) and keep a local one.
    return html(t'<input type="text" ref={[local, props.ref]}>')
```

Refs are assigned during mount, so read them in
[`on_settled`][wybthon.on_settled], an effect, or an event handler, not
at the top of the component body. The `ref` attribute (or the helpers'
`ref=` prop) also accepts a callback that receives the `Element`, which
is closer to Solid 2.0's function refs:

```python
def measure(el):
    print(el.element.offsetWidth)


html(t"<div ref={measure}>Sized</div>")
html(t"<div ref={(lambda el: el.element.focus())}>Inline</div>")  # an inline lambda needs parentheses
```

`Element.query(selector)`, `.find(selector)`, and `.element` commit
pending batched ops first, so nodes created earlier in the same update
are visible to the read.

#### See also

- [Element helpers](elements.md): the `ref=` prop and DOM property rules
- [Events](events.md): `DomEvent.target` and `current_target` are `Element`-backed
- [Concepts: DOM interop](../concepts/dom.md)
