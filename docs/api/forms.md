### wybthon.forms

::: wybthon.forms

#### What's in this module

A small toolkit for controlled forms on top of signals: per-field state,
binding helpers that return prop dicts to spread onto inputs, composable
validators, submit wrappers, and reactive ARIA attributes. Import it
from `wybthon.forms`; these names aren't re-exported from `wybthon`.

| Name | Description |
| --- | --- |
| [`Field`][wybthon.forms.Field] | Reactive state for one field: `value`/`set_value`, `error`/`set_error`, `touched`/`set_touched`, and `.validate(validators)`. |
| [`form_state`][wybthon.forms.form_state] | `{name: initial}` to a [`FormState`][wybthon.forms.FormState]. |
| [`FormState`][wybthon.forms.FormState] | A `{name: Field}` dict with aggregate `dirty`, `validating`, `submitting`, and `submit_error` state, plus `data()`, `reset()`, and `await submit(handler, rules=...)`. |
| [`bind_text`][wybthon.forms.bind_text] | `{"value": accessor, "on_input": handler}` for text inputs, validating on every input event. |
| [`bind_number`][wybthon.forms.bind_number] | Numeric input binding that keeps an empty value as `None`. |
| [`bind_checkbox`][wybthon.forms.bind_checkbox] | `{"checked": accessor, "on_change": handler}` for a boolean field. |
| [`bind_select`][wybthon.forms.bind_select] | `{"value": accessor, "on_change": handler}` for `<select>`. |
| [`bind_multiselect`][wybthon.forms.bind_multiselect] | Binds every selected option of a `<select multiple>` to a list field. |
| [`on_submit`][wybthon.forms.on_submit] | Submit handler that prevents default and calls `handler(form)`. |
| [`on_submit_validated`][wybthon.forms.on_submit_validated] | Same, but validates the whole form against `rules` first. |
| `Validator`, `AsyncValidator` | Type aliases: `(value) -> str | None`, and the same returning an awaitable. |
| [`required`][wybthon.forms.required], [`min_length`][wybthon.forms.min_length], [`max_length`][wybthon.forms.max_length], [`email`][wybthon.forms.email] | Validator factories with optional custom messages. |
| [`validate`][wybthon.forms.validate], [`validate_field`][wybthon.forms.validate_field], [`validate_form`][wybthon.forms.validate_form] | Run validators on a value, a field, or a whole form. |
| [`rules_from_schema`][wybthon.forms.rules_from_schema] | Build a rules map from `{"name": {"required": True, "min_length": 2}, ...}`. |
| [`a11y_control_attrs`][wybthon.forms.a11y_control_attrs] | Reactive `aria_invalid` and `aria_describedby` for a control. |
| [`error_message_attrs`][wybthon.forms.error_message_attrs] | `id`, `role="alert"`, and `aria_live="polite"` for the message container. |

```python
from wybthon import component, html
from wybthon.forms import (
    a11y_control_attrs,
    bind_checkbox,
    bind_text,
    email,
    error_message_attrs,
    form_state,
    on_submit_validated,
    required,
)


@component
def Signup():
    fields = form_state({"name": "", "email": "", "agree": False})
    rules = {"name": [required()], "email": [required(), email()]}
    name = fields["name"]

    def save(f):
        print({k: field.value.peek() for k, field in f.items()})

    return html(t"""
      <form onsubmit={on_submit_validated(rules, save, fields)}>
        <label for="name">Name</label>
        <input
          id="name"
          {bind_text(name, validators=rules["name"])}
          {a11y_control_attrs(name, described_by_id="name-error")}
        >
        <span {error_message_attrs(id="name-error")}>{name.error}</span>
        <label><input type="checkbox" {bind_checkbox(fields["agree"])}> I agree</label>
        <button type="submit">Save</button>
      </form>
    """)
```

- The binding helpers return prop mappings: spread them onto a template
  tag (`<input {bind_text(field)}>`) or an element helper
  (`input_(**bind_text(field))`).
- A field's `error` accessor is `None` while valid, so embedding it as a
  child renders nothing until there's a message.
- `touched` becomes `True` on the first input, so you can delay showing
  errors with a function such as
  `def name_error(): return name.error() if name.touched() else None`.
- `email()` accepts empty values; combine it with `required()`.
- In CPython tests, drive a form with [`wybthon.testing`](testing.md):
  `fire.input(screen.get_by_label_text("Name"), "Ada")`, then
  `fire.submit(form_node)`.

#### See also

- [Events](events.md): the `DomEvent` these handlers receive
- [Element helpers](elements.md): why `value` and `checked` are DOM properties
- [Concepts: Forms](../concepts/forms.md)
- [Examples: Forms](../examples/forms.md)
