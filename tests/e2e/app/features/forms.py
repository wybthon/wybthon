"""Forms: form_state, two-way bindings, live validation, and validated submit."""

from app.testkit import tid

from wybthon import (
    a11y_control_attrs,
    bind_checkbox,
    bind_select,
    bind_text,
    button,
    component,
    create_signal,
    div,
    dynamic,
    email,
    error_message_attrs,
    form,
    form_state,
    h2,
    input_,
    label,
    min_length,
    on_submit_validated,
    option,
    required,
    select,
    span,
)


@component
def Page():
    fs = form_state({"name": "", "email": "", "subscribe": False, "choice": ""})
    rules = {"name": [required(), min_length(2)], "email": [email()]}

    result, set_result = create_signal("")

    def submit_handler(_form):
        set_result(
            "name={};email={};subscribe={};choice={}".format(
                fs["name"].value.get(),
                fs["email"].value.get(),
                fs["subscribe"].value.get(),
                fs["choice"].value.get(),
            )
        )

    submit = on_submit_validated(rules, submit_handler, fs)

    name_field = fs["name"]
    email_field = fs["email"]

    return div(
        h2("Forms"),
        form(
            div(
                input_(
                    type="text",
                    **bind_text(name_field, validators=[required(), min_length(2)]),
                    **a11y_control_attrs(name_field, described_by_id="f-name-err"),
                    **tid("form-name"),
                ),
                span(
                    dynamic(lambda: name_field.error.get() or ""),
                    **error_message_attrs(id="f-name-err"),
                    **tid("form-name-err"),
                ),
            ),
            div(
                input_(
                    type="email",
                    **bind_text(email_field, validators=[email()]),
                    **tid("form-email"),
                ),
                span(dynamic(lambda: email_field.error.get() or ""), **tid("form-email-err")),
            ),
            label(input_(type="checkbox", **bind_checkbox(fs["subscribe"]), **tid("form-sub")), " subscribe"),
            select(
                option("--", value=""),
                option("Option A", value="a"),
                option("Option B", value="b"),
                **bind_select(fs["choice"]),
                **tid("form-choice"),
            ),
            button("Submit", type="submit", **tid("form-submit")),
            on_submit=submit,
        ),
        span(result, **tid("form-result")),
        **tid("page-forms"),
    )
