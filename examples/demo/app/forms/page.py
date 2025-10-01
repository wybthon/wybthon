from wybthon import (
    Component,
    h,
    form_state,
    bind_text,
    bind_checkbox,
    bind_select,
    on_submit,
    required,
    min_length,
    email,
)


class FormsPage(Component):
    def __init__(self, props):
        super().__init__(props)
        self.form = form_state({
            "name": "",
            "email": "",
            "subscribe": False,
            "choice": "",
        })

        def submit_handler(_form):
            name = self.form["name"].value.get()
            email_val = self.form["email"].value.get()
            self._result = (
                f"Submitted: name={name}, email={email_val}, "
                f"subscribe={self.form['subscribe'].value.get()}, "
                f"choice={self.form['choice'].value.get()}"
            )

        self._on_submit = on_submit(submit_handler, self.form)

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

        return h(
            "div",
            {},
            h("h3", {}, "Forms Demo"),
            h("form", {"on_submit": getattr(self, "_on_submit", lambda e: None)},
              h("div", {},
                h("label", {}, "Name: "),
                h("input", {"type": "text", **name_bind}),
                h("span", {"style": {"color": "red"}}, name_field.error.get() or ""),
              ),
              h("div", {},
                h("label", {}, "Email: "),
                h("input", {"type": "email", **email_bind}),
                h("span", {"style": {"color": "red"}}, email_field.error.get() or ""),
              ),
              h("div", {},
                h("label", {},
                  h("input", {"type": "checkbox", **sub_bind}),
                  " Subscribe to newsletter",
                ),
              ),
              h("div", {},
                h("label", {}, "Choice: "),
                h("select", {**choice_bind},
                  h("option", {"value": ""}, "--"),
                  h("option", {"value": "a"}, "Option A"),
                  h("option", {"value": "b"}, "Option B"),
                ),
              ),
              h("button", {"type": "submit"}, "Submit"),
            ),
            h("p", {}, result_text),
        )
