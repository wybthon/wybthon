### wybthon.forms

::: wybthon.forms

#### What's in this module

A small toolkit for controlled forms on top of signals: per-field state,
binding helpers that return prop dicts to spread onto inputs, composable
validators, submit wrappers, and reactive ARIA attributes.

| Name | Description |
| --- | --- |
| [`Field`][wybthon.Field] | Reactive state for one field: `value`/`set_value`, `error`/`set_error`, `touched`/`set_touched`, and `.validate(validators)`. |
| [`form_state`][wybthon.form_state] | `{name: initial}` to `{name: Field}`. |
| [`bind_text`][wybthon.bind_text] | `{"value": accessor, "on_input": handler}` for text inputs, validating on every input event. |
| [`bind_checkbox`][wybthon.bind_checkbox] | `{"checked": accessor, "on_change": handler}` for a boolean field. |
| [`bind_select`][wybthon.bind_select] | `{"value": accessor, "on_change": handler}` for `<select>`. |
| [`on_submit`][wybthon.on_submit] | Submit handler that prevents default and calls `handler(form)`. |
| [`on_submit_validated`][wybthon.on_submit_validated] | Same, but validates the whole form against `rules` first. |
| [`Validator`][wybthon.Validator] | Type alias: `(value) -> str | None`. |
| [`required`][wybthon.required], [`min_length`][wybthon.min_length], [`max_length`][wybthon.max_length], [`email`][wybthon.email] | Validator factories with optional custom messages. |
| [`validate`][wybthon.validate], [`validate_field`][wybthon.validate_field], [`validate_form`][wybthon.validate_form] | Run validators on a value, a field, or a whole form. |
| [`rules_from_schema`][wybthon.rules_from_schema] | Build a rules map from `{"name": {"required": True, "min_length": 2}, ...}`. |
| [`a11y_control_attrs`][wybthon.a11y_control_attrs] | Reactive `aria_invalid` and `aria_describedby` for a control. |
| [`error_message_attrs`][wybthon.error_message_attrs] | `id`, `role="alert"`, and `aria_live="polite"` for the message container. |

```python
from wybthon import (
    a11y_control_attrs, bind_checkbox, bind_text, button, component, email, error_message_attrs,
    form, form_state, input_, label, on_submit_validated, required, span,
)

@component
def Signup():
    fields = form_state({"name": "", "email": "", "agree": False})
    rules = {"name": [required()], "email": [required(), email()]}

    def save(f):
        print({k: field.value.peek() for k, field in f.items()})

    return form(
        label("Name", html_for="name"),
        input_(
            id="name",
            **bind_text(fields["name"], validators=rules["name"]),
            **a11y_control_attrs(fields["name"], described_by_id="name-error"),
        ),
        span(fields["name"].error, **error_message_attrs(id="name-error")),
        label(input_(type="checkbox", **bind_checkbox(fields["agree"])), " I agree"),
        button("Save", type="submit"),
        on_submit=on_submit_validated(rules, save, fields),
    )
```

- A field's `error` accessor is `None` while valid, so embedding it as a
  child renders nothing until there's a message.
- `touched` becomes `True` on the first input, so you can delay showing
  errors: `lambda: fields["name"].error() if fields["name"].touched() else None`.
- `email()` accepts empty values; combine it with `required()`.

#### See also

- [Events](events.md): the `DomEvent` these handlers receive
- [Props](props.md): why `value` and `checked` are DOM properties
- [Concepts: Forms](../concepts/forms.md)
- [Examples: Forms](../examples/forms.md)
