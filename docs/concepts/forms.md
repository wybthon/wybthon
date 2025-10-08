### Forms

Form state helpers, validators, aggregated validation, and accessibility patterns.

```python
from wybthon import (
    h,
    form_state,
    bind_text,
    bind_checkbox,
    bind_select,
    required,
    min_length,
    email,
    validate_form,
    on_submit_validated,
    a11y_control_attrs,
    error_message_attrs,
)

fields = form_state({"name": "", "email": "", "agree": False, "choice": ""})

rules = {
    "name": [required(), min_length(2)],
    "email": [email()],
    # "choice": [required()],  # optional demo rule
}

def View(props):
    name = fields["name"]
    email_field = fields["email"]
    agree = fields["agree"]
    choice = fields["choice"]

    name_bind = bind_text(name, validators=[required(), min_length(2)])
    email_bind = bind_text(email_field, validators=[email()])
    agree_bind = bind_checkbox(agree)
    choice_bind = bind_select(choice)

    on_submit = on_submit_validated(rules, lambda f: print("submit ok"), fields)

    return h(
        "form",
        {"on_submit": on_submit},
        h("label", {"for": "name"}, "Name"),
        h("input", {"id": "name", **name_bind, **a11y_control_attrs(name, described_by_id="name-err")}),
        h("span", {**error_message_attrs(id="name-err")}, name.error.get() or ""),

        h("label", {"for": "email"}, "Email"),
        h("input", {"id": "email", "type": "email", **email_bind, **a11y_control_attrs(email_field, described_by_id="email-err")}),
        h("span", {**error_message_attrs(id="email-err")}, email_field.error.get() or ""),

        h("label", {}, h("input", {"type": "checkbox", **agree_bind}), " Agree"),

        h("label", {"for": "choice"}, "Choice"),
        h("select", {"id": "choice", **choice_bind},
          h("option", {"value": ""}, "--"),
          h("option", {"value": "a"}, "A"),
          h("option", {"value": "b"}, "B")),

        h("button", {"type": "submit"}, "Submit"),
    )
```

Notes:
- Use `validate_form` to aggregate errors and mark fields as touched. It returns `(is_valid, errors_map)`.
- Use `on_submit_validated(rules, handler, form)` to guard submission until the form is valid.
- For accessibility:
  - Set `for` on `label` to match the input `id`.
  - Add `aria-invalid` and `aria-describedby` via `a11y_control_attrs`.
  - Render error containers with `role="alert"`/`aria-live="polite"` using `error_message_attrs`.
