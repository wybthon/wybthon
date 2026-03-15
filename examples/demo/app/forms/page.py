from wybthon import (
    a11y_control_attrs,
    bind_checkbox,
    bind_select,
    bind_text,
    button,
    code,
    component,
    create_signal,
    div,
    email,
    error_message_attrs,
    form,
    form_state,
    h2,
    h3,
    input_,
    label,
    min_length,
    on_submit_validated,
    option,
    p,
    pre,
    required,
    select,
    span,
)


@component
def FormsPage():
    fs = form_state(
        {
            "name": "",
            "email": "",
            "subscribe": False,
            "choice": "",
        }
    )

    rules = {
        "name": [required(), min_length(2)],
        "email": [email()],
    }

    result, set_result = create_signal("")

    def submit_handler(_form):
        name = fs["name"].value.get()
        email_val = fs["email"].value.get()
        set_result(
            f"Submitted: name={name}, email={email_val}, "
            f"subscribe={fs['subscribe'].value.get()}, "
            f"choice={fs['choice'].value.get()}"
        )

    submit = on_submit_validated(rules, submit_handler, fs)

    def render():
        name_field = fs["name"]
        email_field = fs["email"]
        sub_field = fs["subscribe"]
        choice_field = fs["choice"]

        name_bind = bind_text(name_field, validators=[required(), min_length(2)])
        email_bind = bind_text(email_field, validators=[email()])
        sub_bind = bind_checkbox(sub_field)
        choice_bind = bind_select(choice_field)

        result_text = result()

        name_err_id = "name-error"
        email_err_id = "email-error"

        return div(
            div(
                h2("Forms"),
                p("Built-in form state, validation, and two-way data bindings."),
                class_name="page-header",
            ),
            div(
                form(
                    div(
                        label("Name", html_for="name-input"),
                        input_(
                            id="name-input",
                            type="text",
                            **name_bind,
                            **a11y_control_attrs(name_field, described_by_id=name_err_id),
                        ),
                        span(
                            name_field.error.get() or "",
                            style={"color": "var(--error)", "fontSize": "0.8rem"},
                            **error_message_attrs(id=name_err_id),
                        ),
                        class_name="form-group",
                    ),
                    div(
                        label("Email", html_for="email-input"),
                        input_(
                            id="email-input",
                            type="email",
                            **email_bind,
                            **a11y_control_attrs(email_field, described_by_id=email_err_id),
                        ),
                        span(
                            email_field.error.get() or "",
                            style={"color": "var(--error)", "fontSize": "0.8rem"},
                            **error_message_attrs(id=email_err_id),
                        ),
                        class_name="form-group",
                    ),
                    div(
                        label(input_(type="checkbox", **sub_bind), " Subscribe to newsletter"),
                        class_name="form-group",
                    ),
                    div(
                        label("Choice", html_for="choice-select"),
                        select(
                            option("--", value=""),
                            option("Option A", value="a"),
                            option("Option B", value="b"),
                            id="choice-select",
                            **choice_bind,
                        ),
                        class_name="form-group",
                    ),
                    button("Submit", type="submit"),
                    on_submit=submit,
                ),
                p(result_text) if result_text else span(""),
                class_name="demo-section",
            ),
            div(
                h3("Validation Rules"),
                pre(
                    code(
                        "form = form_state({...})\n"
                        "rules = {...}\n"
                        "on_submit = on_submit_validated(rules, handler, form)"
                    ),
                    class_name="code-block",
                ),
                class_name="demo-section",
            ),
            class_name="page",
        )

    return render
