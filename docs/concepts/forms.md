# Forms

Form state helpers, validators, aggregated validation, and accessibility
patterns. Everything here is a thin layer over signals and delegated
events, so you can drop down to plain [`create_signal`][wybthon.create_signal]
and an `oninput` handler whenever the helpers don't fit. Import the helpers from
`wybthon.forms`; they aren't exported from the top-level `wybthon`
package.

```python
from wybthon import component, html
from wybthon.forms import (
    a11y_control_attrs,
    bind_checkbox,
    bind_select,
    bind_text,
    email,
    error_message_attrs,
    form_state,
    min_length,
    on_submit_validated,
    required,
)

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

    return html(t"""
      <form onsubmit={on_submit_validated(rules, save, fields)}>
        <label for="name">Name</label>
        <input
          id="name"
          {bind_text(name, validators=rules["name"])}
          {a11y_control_attrs(name, described_by_id="name-err")}
        >
        <span {error_message_attrs(id="name-err")}>{name.error}</span>

        <label for="email">Email</label>
        <input
          id="email"
          type="email"
          {bind_text(email_field, validators=rules["email"])}
          {a11y_control_attrs(email_field, described_by_id="email-err")}
        >
        <span {error_message_attrs(id="email-err")}>{email_field.error}</span>

        <label><input type="checkbox" {bind_checkbox(fields["agree"])}> Agree</label>

        <label for="choice">Choice</label>
        <select id="choice" {bind_select(fields["choice"])}>
          <option value="">--</option>
          <option value="a">A</option>
          <option value="b">B</option>
        </select>

        <button type="submit">Submit</button>
      </form>
    """)
```

The helpers return prop dicts, which a template applies with a spread
(`<input {attrs}>`). Their keys are the element helpers' Python names
(`on_input`, `aria_invalid`); spreads use the same prop appliers as the
helpers, so the dicts work in both styles. With the element helpers,
spread them as keyword arguments instead:
`input_(id="name", **bind_text(name))`.

## Fields

[`form_state`][wybthon.forms.form_state] turns a dict of initial values into
a [`FormState`][wybthon.forms.FormState] mapping of [`Field`][wybthon.forms.Field] objects. Each field exposes
reactive values:

| Attribute | Type | Meaning |
| --- | --- | --- |
| `value` / `set_value` | `Accessor[T]` / method | The current input value. |
| `error` / `set_error` | `Accessor[str \| None]` | The latest validation message, or `None`. |
| `touched` / `set_touched` | `Accessor[bool]` | `True` once the user has interacted with the field. |

Because these are ordinary accessors, you can render them directly as
children or bindings. `<span>{name.error}</span>` shows the message
reactively and renders nothing while it's `None`;
`field.set_value("...")` from code updates the bound input too.

Use `touched` to hold error display until the user has typed:

```python
def visible_error():
    return name.error() if name.touched() else None


html(t"<span {error_message_attrs(id='name-err')}>{visible_error}</span>")
```

`Field.validate(validators)` runs the rules against the current value,
marks the field touched, and stores the error. It's what the aggregate
helpers call under the hood.

## Bindings

The `bind_*` helpers return prop dicts to spread onto a control
(`<input {bind_text(field)}>`):

- [`bind_text(field, validators=[...])`][wybthon.forms.bind_text] gives `value`, `on_input`, and `on_compositionend`. Composition input waits until composition ends. The `value` entry is the field's accessor, so the DOM follows the signal. Each keystroke stores the value, marks the field touched, and runs the validators.
- [`bind_checkbox(field)`][wybthon.forms.bind_checkbox] gives `checked` and `on_change` for a boolean field.
- [`bind_select(field)`][wybthon.forms.bind_select] gives `value` and `on_change` for a `<select>`.
- [`bind_number(field)`][wybthon.forms.bind_number] and [`bind_multiselect(field)`][wybthon.forms.bind_multiselect] cover numeric inputs and multiple selections; see [Dirty state, reset, and async workflows](#dirty-state-reset-and-async-workflows).

Checkbox and select bindings clear the error on change; text bindings
revalidate on every input event. Add more attributes alongside the
spread as usual: `<input {bind_text(field)} placeholder="Name"
autocomplete="name">`.

## Validators

A `Validator` is a function from a value to an
error string or `None`. The built-ins are factories so messages are
customizable:

```python
from wybthon.forms import email, max_length, min_length, required

rules = {
    "name": [required("Please enter a name"), min_length(2), max_length(40)],
    "email": [required(), email()],
}
```

- [`required`][wybthon.forms.required] rejects `None` and blank strings.
- [`min_length`][wybthon.forms.min_length] and [`max_length`][wybthon.forms.max_length] compare `len(str(value))`.
- [`email`][wybthon.forms.email] checks a lightweight pattern and treats empty values as valid, so pair it with `required` when the field is mandatory.

Write your own by returning a message or `None`:

```python
def matches(other):
    def _v(value):
        return None if value == other.value.peek() else "Passwords don't match"

    return _v
```

[`validate(value, validators)`][wybthon.forms.validate] returns the first
failing message. [`rules_from_schema`][wybthon.forms.rules_from_schema] builds
a rules map from a small declarative dict when you'd rather configure
than compose.

## Submitting

- [`on_submit(handler, form)`][wybthon.forms.on_submit] prevents the default navigation and calls `handler(form)`.
- [`on_submit_validated(rules, handler, form)`][wybthon.forms.on_submit_validated] first runs [`validate_form`][wybthon.forms.validate_form], which validates every field in `rules`, marks them touched, stores their errors, and returns `(is_valid, errors)`. The handler runs only when everything passes.

Both return an event handler for the form's `onsubmit` attribute
(`on_submit` with the helpers). Signal writes inside the handler flush
when it returns, so error messages and `aria-invalid` states update in
one commit.

To validate a single field on blur or on demand, call
[`validate_field(field, validators)`][wybthon.forms.validate_field].

## Accessibility

- Set `for` on a `<label>` to match the control's `id`. With the element helpers, pass `html_for` (or `for_`); the prop applier writes it as the `for` attribute.
- [`a11y_control_attrs(field, described_by_id=...)`][wybthon.forms.a11y_control_attrs] returns reactive `aria_invalid` and `aria_describedby` props: `aria-invalid` is `"true"` while the field has an error, and `aria-describedby` points at the message container only while a message exists, so screen readers don't announce an empty region.
- [`error_message_attrs(id=...)`][wybthon.forms.error_message_attrs] returns `id`, `role="alert"`, and `aria-live="polite"` for the message container.

Because the ARIA props are accessors, they update through fine-grained
bindings without re-rendering the form.

## Controlled inputs without the helpers

The helpers are optional. A controlled input is a signal, a `value`
binding, and an `oninput` handler:

```python
from wybthon import DomEvent, component, create_signal, html


@component
def Search():
    query, set_query = create_signal("")

    def update(e: DomEvent):
        set_query(e.target.value)

    return html(t"<input value={query} oninput={update}>")
```

`e.target.value` is read from the dispatch payload, not from the DOM,
so it's cheap even in large lists. See [Events](events.md).

## Next steps

- See the [Forms example](../examples/forms.md) for an end-to-end form.
- Browse the [`forms`](../api/forms.md) API reference for every helper.
- Read [Events](events.md) for delegated handler details.

## Dirty state, reset, and async workflows

Each field has `dirty` and `validating` accessors. `field.reset()` restores its initial value and clears touched and error state; `field.reset(value)` establishes a new baseline. [`FormState`][wybthon.forms.FormState]'s `dirty` and `validating` accessors aggregate its fields, `.data()` returns current values, and `.reset(values=None)` resets the form.

`await field.validate_async(validators)` accepts synchronous or async validators (`AsyncValidator`). Editing the value cancels stale validation, and a response for an old revision can't overwrite the current error. Owning scope disposal cancels validation too.

```python
async def save(values):
    return await post_profile(values)


async def submit(event):
    event.prevent_default()
    await fields.submit(save, rules=rules)


html(t"""
  <form onsubmit={submit}>
    <input {bind_text(fields["name"])}>
    <button type="submit">Save</button>
  </form>
""")
```

`FormState.submit` validates the fields, snapshots their values, and awaits the handler. `.submitting` and `.submit_error` expose the result. If values change during validation, that submission doesn't send stale values. The simpler `on_submit` helpers also propagate async handler results to the event task.

`bind_text(field, parse=..., format=...)` separates display text from stored values and reports conversion errors. `bind_number(field)` handles numeric values and stores an empty input as `None`. `bind_multiselect(field)` binds a list of selected values through `selected_values`, with no per-option Python-to-JS reads. Controlled selections are applied after options are inserted or replaced.
