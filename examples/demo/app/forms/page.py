from wybthon import (
    Component,
    a11y_control_attrs,
    bind_checkbox,
    bind_select,
    bind_text,
    email,
    error_message_attrs,
    form_state,
    h,
    min_length,
    on_submit_validated,
    required,
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

        # Validation rules for submit gating
        self._rules = {
            "name": [required(), min_length(2)],
            "email": [email()],
            # Example: make choice required in demo
            # "choice": [required()],
        }

        def submit_handler(_form):
            name = self.form["name"].value.get()
            email_val = self.form["email"].value.get()
            self._result = (
                f"Submitted: name={name}, email={email_val}, "
                f"subscribe={self.form['subscribe'].value.get()}, "
                f"choice={self.form['choice'].value.get()}"
            )

        # Only invoke handler when form validates
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

        # Accessibility: link controls to their error messages
        name_err_id = "name-error"
        email_err_id = "email-error"

        return h(
            "div",
            {},
            h("h3", {}, "Forms Demo"),
            h(
                "form",
                {"on_submit": getattr(self, "_on_submit", lambda e: None)},
                h(
                    "div",
                    {},
                    h("label", {"for": "name-input"}, "Name: "),
                    h(
                        "input",
                        {
                            "id": "name-input",
                            "type": "text",
                            **name_bind,
                            **a11y_control_attrs(name_field, described_by_id=name_err_id),
                        },
                    ),
                    h(
                        "span",
                        {"style": {"color": "red"}, **error_message_attrs(id=name_err_id)},
                        name_field.error.get() or "",
                    ),
                ),
                h(
                    "div",
                    {},
                    h("label", {"for": "email-input"}, "Email: "),
                    h(
                        "input",
                        {
                            "id": "email-input",
                            "type": "email",
                            **email_bind,
                            **a11y_control_attrs(email_field, described_by_id=email_err_id),
                        },
                    ),
                    h(
                        "span",
                        {"style": {"color": "red"}, **error_message_attrs(id=email_err_id)},
                        email_field.error.get() or "",
                    ),
                ),
                h(
                    "div",
                    {},
                    h(
                        "label",
                        {},
                        h("input", {"type": "checkbox", **sub_bind}),
                        " Subscribe to newsletter",
                    ),
                ),
                h(
                    "div",
                    {},
                    h("label", {"for": "choice-select"}, "Choice: "),
                    h(
                        "select",
                        {"id": "choice-select", **choice_bind},
                        h("option", {"value": ""}, "--"),
                        h("option", {"value": "a"}, "Option A"),
                        h("option", {"value": "b"}, "Option B"),
                    ),
                ),
                h("button", {"type": "submit"}, "Submit"),
            ),
            h("p", {}, result_text),
        )
