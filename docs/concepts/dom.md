### DOM Interop

`Element` is a thin wrapper around DOM nodes with helpers for attributes, classes, events, and querying.

```python
from wybthon.dom import Element

root = Element("#app", existing=True)
div = Element("div")
div.set_text("Hello")
div.append_to(root)
```

> TODO: Explain refs and how VDOM uses `Element` under the hood.
