### Events

Event handlers are delegated at the document root.

```python
from wybthon import h

def Button(props):
    return h("button", {"on_click": lambda evt: print("clicked")}, "Click")
```

Supported prop names: `on_click`, `on_input`, `on_change`, etc. Both `on_foo` and `onFoo` styles are supported; they normalize to DOM event names.

> TODO: Document `DomEvent` shape and `prevent_default`/`stop_propagation`.
