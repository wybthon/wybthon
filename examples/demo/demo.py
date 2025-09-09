from wybthon import (
    Element,
    h,
    render,
    Component,
    signal,
    create_context,
    use_context,
    Provider,
    Router,
    Route,
    Link,
    use_resource,
    ErrorBoundary,
    form_state,
    bind_text,
    bind_checkbox,
    bind_select,
    on_submit,
    validate,
    required,
    min_length,
    email,
)


# Function component example
def Hello(props):
    name = props.get("name", "world")
    return h("h2", {"class": "hello"}, f"Hello, {name}!")


# Class component example with simple lifecycle hooks
class Counter(Component):
    def __init__(self, props):
        super().__init__(props)
        self.count = signal(0)
        # Define handler early so initial render binds it
        def inc(_evt):
            print("Increment clicked")
            self.count.set(self.count.get() + 1)
        self._inc = inc

    def on_mount(self):
        print("Counter mounted with initial count:", self.count.get())

    def render(self):
        print("Counter render; count=", self.count.get())
        return h(
            "div",
            {"class": "counter"},
            h("p", {}, f"Count: {self.count.get()}"),
            h("button", {"on_click": getattr(self, "_inc", lambda e: None)}, "Increment"),
        )


# Context example
Theme = create_context("light")


def ThemeLabel(props):
    return h("p", {}, f"Theme: {use_context(Theme)}")


async def main():
    # Build a small VDOM tree containing both components
    routes = [
        Route(path="/", component=lambda p: h("div", {}, h("p", {}, "Home"))),
        Route(path="/about", component=lambda p: h("div", {}, h("p", {}, "About"))),
        Route(path="/fetch", component=lambda p: h(FetchDemo, {})),
        Route(path="/forms", component=lambda p: h(FormDemo, {})),
        Route(path="/errors", component=lambda p: h(ErrorBoundaryDemo, {})),
    ]

    tree = h(
        "div",
        {"id": "app"},
        h("h1", {}, "Wybthon VDOM Demo"),
        h("nav", {},
          h(Link, {"to": "/"}, "Home"), " | ",
          h(Link, {"to": "/about"}, "About"), " | ",
          h(Link, {"to": "/fetch"}, "Fetch"), " | ",
          h(Link, {"to": "/forms"}, "Forms"), " | ",
          h(Link, {"to": "/errors"}, "Errors"),
        ),
        h(Router, {"routes": routes}),
        h(Provider, {"context": Theme, "value": "dark"},
          h(ThemeLabel, {}),
          h(Counter, {}),
        ),
        h(Hello, {"name": "Python"}),
    )

    container = Element("body", existing=True)
    render(tree, container)


class FetchDemo(Component):
    def __init__(self, props):
        super().__init__(props)

        async def fetcher(signal=None):
            import importlib

            js = importlib.import_module("js")
            if signal is not None:
                resp = await js.fetch("https://jsonplaceholder.typicode.com/todos/1", {"signal": signal})
            else:
                resp = await js.fetch("https://jsonplaceholder.typicode.com/todos/1")
            data = await resp.json()
            title = str(getattr(data, "title", "unknown"))
            return f"Todo: {title}"

        self.res = use_resource(fetcher)

        def on_reload(_evt):
            self.res.reload()

        def on_cancel(_evt):
            self.res.cancel()

        self._on_reload = on_reload
        self._on_cancel = on_cancel

    def on_unmount(self):
        try:
            self.res.cancel()
        except Exception:
            pass

    def render(self):
        status_text = "Loading..." if self.res.loading.get() else (
            str(self.res.error.get()) if self.res.error.get() else self.res.data.get() or "No data"
        )
        return h(
            "div",
            {},
            h("h3", {}, "Async Fetch Demo"),
            h("p", {}, status_text),
            h("button", {"on_click": getattr(self, "_on_reload", lambda e: None)}, "Reload"),
            h("button", {"on_click": getattr(self, "_on_cancel", lambda e: None)}, "Cancel"),
        )


class FormDemo(Component):
    def __init__(self, props):
        super().__init__(props)
        self.form = form_state({
            "name": "",
            "email": "",
            "subscribe": False,
            "choice": "",
        })

        def submit_handler(form):
            name = self.form["name"].value.get()
            email_val = self.form["email"].value.get()
            self._result = f"Submitted: name={name}, email={email_val}, subscribe={self.form['subscribe'].value.get()}, choice={self.form['choice'].value.get()}"

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


class ErrorBoundaryDemo(Component):
    def render(self):
        def Bug(_props):
            raise RuntimeError("Boom")

        return h(
            ErrorBoundary,
            {"fallback": lambda err: h("div", {"style": {"color": "crimson"}}, f"Caught error: {err}")},
            h("div", {},
              h("p", {}, "This component will throw:"),
              h(Bug, {}),
            ),
        )
