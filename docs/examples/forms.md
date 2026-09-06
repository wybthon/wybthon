# Forms

Bindings, validation, an aggregated submit handler, and accessible error messages.

```python
from wybthon import (
    Show,
    a11y_control_attrs,
    bind_checkbox,
    bind_select,
    bind_text,
    button,
    component,
    email,
    error_message_attrs,
    form,
    form_state,
    input_,
    label,
    min_length,
    on_submit_validated,
    option,
    p,
    render,
    required,
    select,
    span,
)


@component
def SignupForm():
    fields = form_state({"name": "", "email": "", "plan": "free", "subscribe": False})
    rules = {
        "name": [required(), min_length(2)],
        "email": [required(), email()],
    }

    def save(f):
        print({k: field.value.peek() for k, field in f.items()})

    name = fields["name"]
    mail = fields["email"]
    plan = fields["plan"]
    subscribe = fields["subscribe"]

    return form(
        p(
            label("Name", html_for="name"),
            input_(
                id="name",
                **bind_text(name, validators=rules["name"]),
                **a11y_control_attrs(name, described_by_id="name-err"),
            ),
            span(name.error, **error_message_attrs(id="name-err")),
        ),
        p(
            label("Email", html_for="email"),
            input_(
                id="email",
                type="email",
                **bind_text(mail, validators=rules["email"]),
                **a11y_control_attrs(mail, described_by_id="email-err"),
            ),
            span(mail.error, **error_message_attrs(id="email-err")),
        ),
        p(
            label("Plan", html_for="plan"),
            select(
                option("Free", value="free"),
                option("Pro", value="pro"),
                id="plan",
                **bind_select(plan),
            ),
        ),
        p(
            label(input_(type="checkbox", **bind_checkbox(subscribe)), " Subscribe to the newsletter"),
        ),
        Show(lambda: plan.value() == "pro", lambda: p("Pro plans are billed monthly.")),
        button("Sign up", type="submit"),
        on_submit=on_submit_validated(rules, save, fields),
    )


render(SignupForm(), "#app")
```

## How it works

- [`form_state`][wybthon.form_state] returns a dict of [`Field`][wybthon.Field] objects. Each field carries `value`, `error`, and `touched` accessors with matching setters, so every piece of form state is a signal.
- [`bind_text`][wybthon.bind_text] returns `{"value": field.value, "on_input": handler}`. The `value` entry is the accessor itself, so programmatic writes through `field.set_value(...)` update the input too. Validators run on every `input` event.
- `span(name.error, ...)` places the error accessor in the tree, so the message appears and disappears as validation runs.
- [`a11y_control_attrs`][wybthon.a11y_control_attrs] produces reactive `aria-invalid` and `aria-describedby` props; [`error_message_attrs`][wybthon.error_message_attrs] marks the message container as a polite live region.
- [`on_submit_validated`][wybthon.on_submit_validated] calls `prevent_default()`, validates every field in `rules` (marking them touched), and only invokes `save` when all pass. Use [`on_submit`][wybthon.on_submit] when you want to handle validation yourself.
- A `Field` is a container of accessors, not an accessor itself, so the `Show` condition reads `plan.value()`.

## Schema-driven rules

[`rules_from_schema`][wybthon.rules_from_schema] builds the validators map from a small declarative schema:

```python
from wybthon import rules_from_schema

rules = rules_from_schema(
    {
        "name": {"required": True, "min_length": 2},
        "email": {"required": "Email is required", "email": True},
    }
)
```

## Validating on demand

Call [`validate_form`][wybthon.validate_form] to validate everything and get an `(is_valid, errors)` tuple, or [`validate_field`][wybthon.validate_field] for one field:

```python
from wybthon import validate_field, validate_form

ok, errors = validate_form(fields, rules)
validate_field(fields["name"], rules["name"])
```

## Next steps

- Read the [Forms](../concepts/forms.md) concept page for the full API surface.
- Browse the [`forms`][wybthon.forms] API reference.
- See [Events](../concepts/events.md) for delegated handler details.
