### Context

Provide and consume values across the tree.

```python
from wybthon import h
from wybthon.context import create_context, Provider, use_context

Theme = create_context("light")

def Label(props):
    theme = use_context(Theme)
    return h("span", {}, f"Theme: {theme}")

view = h(Provider, {"context": Theme, "value": "dark", "children": [h(Label, {})]})
```

> TODO: Document provider scoping and performance notes.
