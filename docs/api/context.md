### wybthon.context

::: wybthon.context

#### What's in this module

Context passes a value down the tree without threading props. A
[`Context`][wybthon.Context] created by
[`create_context`][wybthon.create_context] **is its own provider**: call
it with a value and children to expose that value to every descendant,
and read it with [`use_context`][wybthon.use_context]. Values live on the
ownership tree, so `use_context` works anywhere an owner exists:
component bodies, effects, memos, and `For` rows.

| Name | Description |
| --- | --- |
| [`create_context`][wybthon.create_context] | `create_context(default=..., *, name=None)`; without a default, reading outside a provider raises. |
| [`Context`][wybthon.Context] | The token; `Theme(value, *children)` returns a provider `VNode`. `.default`, `.name`, `.has_default`. |
| [`use_context`][wybthon.use_context] | Nearest provided value, returned exactly as provided (an accessor stays an accessor). |
| [`ContextNotFoundError`][wybthon.ContextNotFoundError] | Raised when no provider is above the reader and the context has no default. |

The value is handed to consumers exactly as provided, so pass a signal
or accessor when consumers should react to changes, and call it where
you need the value.

```python
from wybthon import Accessor, Context, button, component, create_context, create_signal, div, use_context

Theme: Context[Accessor[str]] = create_context(name="Theme")

@component
def ThemedButton():
    theme = use_context(Theme)                     # the accessor the provider passed
    return button("Hi", class_=lambda: f"btn-{theme()}")

@component
def App():
    theme, set_theme = create_signal("light")
    return Theme(                                  # value first, then children
        theme,
        div(
            ThemedButton(),
            button("Toggle", on_click=lambda e: set_theme("dark" if theme.peek() == "light" else "light")),
        ),
    )
```

Nested providers for the same context shadow outer ones. Outside a
component, `use_context` still works inside any reactive scope
(`create_root`, an effect, a memo).

#### See also

- [Concepts: Context](../concepts/context.md)
- [`Owner`][wybthon.Owner]: where context values are stored
- [Router](router.md): `use_params`, `use_query`, and `use_base_path` are context readers
