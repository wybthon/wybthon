from wybthon import Component, button, computed, div, li, p, signal, ul


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
        items = [li(n) for n in self.names.get()]
        return div(
            p(f"Total: {len(self.names.get())} | Starts with A: {self.starts_with_a.get()}"),
            div(
                button("+ Ada", on_click=getattr(self, "_add_ada", lambda e: None)),
                button("+ Alan", on_click=getattr(self, "_add_alan", lambda e: None)),
                button("Clear", on_click=getattr(self, "_clear", lambda e: None)),
            ),
            ul(items),
        )
