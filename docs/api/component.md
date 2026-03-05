### wybthon.component

::: wybthon.component

#### forward_ref

`forward_ref(render_fn)` creates a component that receives a `ref` prop and forwards it to a child element.

The wrapped function receives `(props, ref)` instead of `(props,)`.

```python
from wybthon import forward_ref, h

FancyInput = forward_ref(lambda props, ref: h("input", {"type": "text", "ref": ref, **props}))

# Usage
h(FancyInput, {"ref": my_ref, "placeholder": "Type here..."})
```
