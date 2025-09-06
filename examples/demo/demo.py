from wybthon import Element, h, render, Component, signal, create_context, use_context, Provider, Router, Route, Link


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
    ]

    tree = h(
        "div",
        {"id": "app"},
        h("h1", {}, "Wybthon VDOM Demo"),
        h("nav", {},
          h(Link, {"to": "/"}, "Home"), " | ",
          h(Link, {"to": "/about"}, "About"),
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
