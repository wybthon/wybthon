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

#### Styles and dataset via VDOM

- Use the `style` prop with a dict of camelCase keys; the VDOM converts to kebab-case and calls `style.setProperty`. Missing keys on update are removed. Passing `None` clears previous styles.
- Use the `dataset` prop with a dict; entries render as `data-*` attributes. Missing keys on update are removed. Passing `None` clears previous dataset entries.
