"""Form with validation — declarative rules, real-time errors.

Tweet caption:
    A validated sign-up form in Python. `required`, `min_length`, `email`
    — all declarative. Errors render live as the user types.

Why it's interesting:
    `form_state` gives you a dict of `FieldState`s, each with `.value`
    and `.error` signals. `bind_text` wires the input two-way.
    `on_submit_validated` blocks submission until every rule passes.
"""

from wybthon import (
    bind_text,
    button,
    component,
    create_signal,
    div,
    dynamic,
    email,
    form,
    form_state,
    input_,
    label,
    min_length,
    on_submit_validated,
    p,
    required,
    span,
)


@component
def SignUpForm():
    fs = form_state({"name": "", "email": ""})
    rules = {"name": [required(), min_length(2)], "email": [required(), email()]}
    result, set_result = create_signal("")

    def handle(_form):
        set_result(f"Welcome, {fs['name'].value.get()}!")

    submit = on_submit_validated(rules, handle, fs)

    return form(
        div(
            label("Name"),
            input_(**bind_text(fs["name"], validators=rules["name"])),
            span(dynamic(lambda: fs["name"].error.get() or ""), style={"color": "crimson"}),
        ),
        div(
            label("Email"),
            input_(type="email", **bind_text(fs["email"], validators=rules["email"])),
            span(dynamic(lambda: fs["email"].error.get() or ""), style={"color": "crimson"}),
        ),
        button("Sign up", type="submit"),
        p(dynamic(result)),
        on_submit=submit,
    )
