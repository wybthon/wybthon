from wybthon import Component, computed, h, signal


class NamesList(Component):
    def __init__(self, props):
        super().__init__(props)
        self.names = signal([])
        self.starts_with_a = computed(lambda: len([n for n in self.names.get() if str(n).lower().startswith("a")]))

        def make_add(name):
            return lambda _evt: self.names.set(self.names.get() + [name])

        def clear(_evt):
            self.names.set([])

        self._add_ada = make_add("Ada")
        self._add_alan = make_add("Alan")
        self._clear = clear

    def render(self):
        items = [h("li", {}, n) for n in self.names.get()]
        return h(
            "div",
            {},
            h("p", {}, f"Total: {len(self.names.get())} | Starts with A: {self.starts_with_a.get()}"),
            h(
                "div",
                {},
                h("button", {"on_click": getattr(self, "_add_ada", lambda e: None)}, "+ Ada"),
                h("button", {"on_click": getattr(self, "_add_alan", lambda e: None)}, "+ Alan"),
                h("button", {"on_click": getattr(self, "_clear", lambda e: None)}, "Clear"),
            ),
            h("ul", {}, items),
        )
