### Forms

Bindings, validation, aggregated submit, and a11y.

```python
from wybthon import (
    h,
    form_state,
    bind_text,
    bind_checkbox,
    required,
    min_length,
    on_submit_validated,
    a11y_control_attrs,
    error_message_attrs,
)

fields = form_state({"name": "", "subscribe": False})
rules = {"name": [required(), min_length(2)]}

def View(props):
    name = fields["name"]
    subscribe = fields["subscribe"]

    submit = on_submit_validated(rules, lambda f: print("OK"), fields)

    return h(
        "form",
        {"on_submit": submit},
        h("label", {"for": "name"}, "Name"),
        h("input", {"id": "name", **bind_text(name, validators=rules["name"]), **a11y_control_attrs(name, described_by_id="name-err")}),
        h("span", {**error_message_attrs(id="name-err")}, name.error.get() or ""),
        h("label", {}, h("input", {"type": "checkbox", **bind_checkbox(subscribe)}), " Subscribe"),
        h("button", {"type": "submit"}, "Submit"),
    )
```

Tips:
- Call `on_submit_validated` to block submission until fields validate.
- Use `a11y_control_attrs` and `error_message_attrs` to wire up errors for assistive tech.
