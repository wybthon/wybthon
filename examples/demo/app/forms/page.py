from wybthon import (
    Component,
    a11y_control_attrs,
    bind_checkbox,
    bind_select,
    bind_text,
    button,
    code,
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


class FormsPage(Component):
    def __init__(self, props):
        super().__init__(props)
        self.form = form_state(
            {
                "name": "",
                "email": "",
                "subscribe": False,
                "choice": "",
            }
        )

        self._rules = {
            "name": [required(), min_length(2)],
            "email": [email()],
        }

        def submit_handler(_form):
            name = self.form["name"].value.get()
            email_val = self.form["email"].value.get()
            self._result = (
                f"Submitted: name={name}, email={email_val}, "
                f"subscribe={self.form['subscribe'].value.get()}, "
                f"choice={self.form['choice'].value.get()}"
            )

        self._on_submit = on_submit_validated(self._rules, submit_handler, self.form)

    def render(self):
        name_field = self.form["name"]
        email_field = self.form["email"]
        sub_field = self.form["subscribe"]
        choice_field = self.form["choice"]

        name_bind = bind_text(name_field, validators=[required(), min_length(2)])
        email_bind = bind_text(email_field, validators=[email()])
        sub_bind = bind_checkbox(sub_field)
        choice_bind = bind_select(choice_field)

        result_text = getattr(self, "_result", "")

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
                            **a11y_control_attrs(
                                name_field, described_by_id=name_err_id
                            ),
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
                            **a11y_control_attrs(
                                email_field, described_by_id=email_err_id
                            ),
                        ),
                        span(
                            email_field.error.get() or "",
                            style={"color": "var(--error)", "fontSize": "0.8rem"},
                            **error_message_attrs(id=email_err_id),
                        ),
                        class_name="form-group",
                    ),
                    div(
                        label(
                            input_(type="checkbox", **sub_bind),
                            " Subscribe to newsletter",
                        ),
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
                    on_submit=getattr(self, "_on_submit", lambda e: None),
                ),
                p(result_text) if result_text else span(""),
                class_name="demo-section",
            ),
            div(
                h3("Validation Rules"),
                pre(
                    code(
                        "form = form_state({\n"
                        '    "name": "", "email": "",\n'
                        '    "subscribe": False, "choice": "",\n'
                        "})\n"
                        "\n"
                        "rules = {\n"
                        '    "name": [required(), min_length(2)],\n'
                        '    "email": [email()],\n'
                        "}\n"
                        "\n"
                        "on_submit = on_submit_validated(rules, handler, form)"
                    ),
                    class_name="code-block",
                ),
                class_name="demo-section",
            ),
            class_name="page",
        )
