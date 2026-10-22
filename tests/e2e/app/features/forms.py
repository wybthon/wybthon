"""Forms: form_state, two-way bindings, live validation, and validated submit.

The ``bind_*`` and ``*_attrs`` helpers return props mappings that are
spread onto the elements: ``<input {bind_text(field)}>``.
"""

from wybthon import component, create_signal, html
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


@component
def Page():
    fs = form_state({"name": "", "email": "", "subscribe": False, "choice": ""})
    rules = {"name": [required(), min_length(2)], "email": [email()]}

    result, set_result = create_signal("")

    def submit_handler(fields):
        set_result(
            "name={};email={};subscribe={};choice={}".format(
                fields["name"].value.peek(),
                fields["email"].value.peek(),
                fields["subscribe"].value.peek(),
                fields["choice"].value.peek(),
            )
        )

    submit = on_submit_validated(rules, submit_handler, fs)

    name_field = fs["name"]
    email_field = fs["email"]
    name_binding = bind_text(name_field, validators=[required(), min_length(2)])
    name_a11y = a11y_control_attrs(name_field, described_by_id="f-name-err")

    return html(t"""
      <div data-testid="page-forms">
        <h2>Forms</h2>
        <form onsubmit={submit}>
          <div>
            <input type="text" {name_binding} {name_a11y} data-testid="form-name">
            <span {error_message_attrs(id="f-name-err")} data-testid="form-name-err">{name_field.error() or ""}</span>
          </div>
          <div>
            <input type="email" {bind_text(email_field, validators=[email()])} data-testid="form-email">
            <span data-testid="form-email-err">{email_field.error() or ""}</span>
          </div>
          <label><input type="checkbox" {bind_checkbox(fs["subscribe"])} data-testid="form-sub"> subscribe</label>
          <select {bind_select(fs["choice"])} data-testid="form-choice">
            <option value="">--</option>
            <option value="a">Option A</option>
            <option value="b">Option B</option>
          </select>
          <button type="submit" data-testid="form-submit">Submit</button>
        </form>
        <span data-testid="form-result">{result()}</span>
      </div>
    """)
