# Forms

Form state helpers, validators, aggregated validation, and accessibility
patterns. Everything here is a thin layer over signals and delegated
events, so you can drop down to plain [`create_signal`][wybthon.create_signal]
and `on_input` whenever the helpers don't fit.

```python
from wybthon import (
    a11y_control_attrs,
    bind_checkbox,
    bind_select,
    bind_text,
    component,
    email,
    error_message_attrs,
    form_state,
    min_length,
    on_submit_validated,
    required,
)
from wybthon.html import button, form, input_, label, option, select, span

fields = form_state({"name": "", "email": "", "agree": False, "choice": ""})

rules = {
    "name": [required(), min_length(2)],
    "email": [email()],
}


@component
def SignupForm():
    name = fields["name"]
    email_field = fields["email"]

    def save(f):
        print({k: field.value.peek() for k, field in f.items()})

    return form(
        label("Name", for_="name"),
        input_(
            id="name",
            **bind_text(name, validators=rules["name"]),
            **a11y_control_attrs(name, described_by_id="name-err"),
        ),
        span(name.error, **error_message_attrs(id="name-err")),
        label("Email", for_="email"),
        input_(
            id="email",
            type="email",
            **bind_text(email_field, validators=rules["email"]),
            **a11y_control_attrs(email_field, described_by_id="email-err"),
        ),
        span(email_field.error, **error_message_attrs(id="email-err")),
        label(input_(type="checkbox", **bind_checkbox(fields["agree"])), " Agree"),
        label("Choice", for_="choice"),
        select(
            option("--", value=""),
            option("A", value="a"),
            option("B", value="b"),
            id="choice",
            **bind_select(fields["choice"]),
        ),
        button("Submit", type="submit"),
        on_submit=on_submit_validated(rules, save, fields),
    )
```

## Fields

[`form_state`][wybthon.form_state] turns a dict of initial values into
a `FormState` mapping of [`Field`][wybthon.Field] objects. Each field exposes
reactive values:

| Attribute | Type | Meaning |
| --- | --- | --- |
| `value` / `set_value` | `Accessor[T]` / `Setter[T]` | The current input value. |
| `error` / `set_error` | `Accessor[str \| None]` | The latest validation message, or `None`. |
| `touched` / `set_touched` | `Accessor[bool]` | `True` once the user has interacted with the field. |

Because these are ordinary accessors, you can render them directly as
children or bindings. `span(name.error)` shows the message reactively
and renders nothing while it's `None`; `field.set_value("...")` from
code updates the bound input too.

Use `touched` to hold error display until the user has typed:

```python
span(lambda: name.error() if name.touched() else None, **error_message_attrs(id="name-err"))
```

`Field.validate(validators)` runs the rules against the current value,
marks the field touched, and stores the error. It's what the aggregate
helpers call under the hood.

## Bindings

The `bind_*` helpers return prop dicts to spread onto a control:

- [`bind_text(field, validators=[...])`][wybthon.bind_text] gives `value`, `on_input`, and `on_compositionend`. Composition input waits until composition ends. The `value` entry is the field's accessor, so the DOM follows the signal. Each keystroke stores the value, marks the field touched, and runs the validators.
- [`bind_checkbox(field)`][wybthon.bind_checkbox] gives `checked` and `on_change` for a boolean field.
- [`bind_select(field)`][wybthon.bind_select] gives `value` and `on_change` for a `<select>`.

Checkbox and select bindings clear the error on change; text bindings
revalidate on every input event. Add more props alongside the spread
(`placeholder`, `class_`, `autocomplete`) as usual.

## Validators

A `Validator` is a function from a value to an
error string or `None`. The built-ins are factories so messages are
customizable:

```python
from wybthon import email, max_length, min_length, required

rules = {
    "name": [required("Please enter a name"), min_length(2), max_length(40)],
    "email": [required(), email()],
}
```

- [`required`][wybthon.required] rejects `None` and blank strings.
- [`min_length`][wybthon.min_length] and [`max_length`][wybthon.max_length] compare `len(str(value))`.
- [`email`][wybthon.email] checks a lightweight pattern and treats empty values as valid, so pair it with `required` when the field is mandatory.

Write your own by returning a message or `None`:

```python
def matches(other):
    def _v(value):
        return None if value == other.value.peek() else "Passwords don't match"

    return _v
```

[`validate(value, validators)`][wybthon.validate] returns the first
failing message. [`rules_from_schema`][wybthon.rules_from_schema] builds
a rules map from a small declarative dict when you'd rather configure
than compose.

## Submitting

- [`on_submit(handler, form)`][wybthon.on_submit] prevents the default navigation and calls `handler(form)`.
- [`on_submit_validated(rules, handler, form)`][wybthon.on_submit_validated] first runs [`validate_form`][wybthon.validate_form], which validates every field in `rules`, marks them touched, stores their errors, and returns `(is_valid, errors)`. The handler runs only when everything passes.

Both return an event handler for the form's `on_submit` prop. Signal
writes inside the handler flush when it returns, so error messages and
`aria-invalid` states update in one commit.

To validate a single field on blur or on demand, call
[`validate_field(field, validators)`][wybthon.validate_field].

## Accessibility

- Set `for_` on `label` to match the control's `id`.
- [`a11y_control_attrs(field, described_by_id=...)`][wybthon.a11y_control_attrs] returns reactive `aria_invalid` and `aria_describedby` props: `aria-invalid` is `"true"` while the field has an error, and `aria-describedby` points at the message container only while a message exists, so screen readers don't announce an empty region.
- [`error_message_attrs(id=...)`][wybthon.error_message_attrs] returns `id`, `role="alert"`, and `aria-live="polite"` for the message container.

Because the ARIA props are accessors, they update through fine-grained
bindings without re-rendering the form.

## Controlled inputs without the helpers

The helpers are optional. A controlled input is a signal, a `value`
binding, and an `on_input` handler:

```python
from wybthon import component, create_signal
from wybthon.html import input_

@component
def Search():
    query, set_query = create_signal("")
    return input_(value=query, on_input=lambda e: set_query(e.target.value))
```

`e.target.value` is read from the dispatch payload, not from the DOM,
so it's cheap even in large lists. See [Events](events.md).

## Next steps

- See the [Forms example](../examples/forms.md) for an end-to-end form.
- Browse the [`forms`](../api/forms.md) API reference for every helper.
- Read [Events](events.md) for delegated handler details.

## Dirty state, reset, and async workflows

Each field has `dirty` and `validating` accessors. `field.reset()` restores its initial value and clears touched/error state; `field.reset(value)` establishes a new baseline. `FormState.dirty` and `.validating` aggregate fields, `.data()` returns current values, and `.reset(values=None)` resets the form.

`await field.validate_async(validators)` accepts synchronous or async validators. Editing the value cancels stale validation, and a response for an old revision can't overwrite the current error. Owning scope disposal cancels validation too.

```python
async def save(values):
    return await post_profile(values)

async def submit(event):
    event.prevent_default()
    await fields.submit(save, rules=rules)
```

`FormState.submit` validates the fields, snapshots their values, and awaits the handler. `.submitting` and `.submit_error` expose the result. If values change during validation, that submission doesn't send stale values. The simpler `on_submit` helpers also propagate async handler results to the event task.

`bind_text(field, parse=..., format=...)` separates display text from stored values and reports conversion errors. `bind_number` handles numeric values and empty inputs. `bind_multiselect` binds all selected values through `selected_values`, with no per-option Python-to-JS reads. Controlled selections are applied after options are inserted or replaced.
