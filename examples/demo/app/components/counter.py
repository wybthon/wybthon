from wybthon import Component, h, signal


class Counter(Component):
    def __init__(self, props):
        super().__init__(props)
        self.count = signal(0)

        def inc(_evt):
            try:
                self.count.set(self.count.get() + 1)
            except Exception:
                pass

        self._inc = inc

    def on_mount(self):
        try:
            print("Counter mounted with initial count:", self.count.get())
        except Exception:
            pass

    def render(self):
        return h(
            "div",
            {"class": "counter"},
            h("p", {}, f"Count: {self.count.get()}"),
            h("button", {"on_click": getattr(self, "_inc", lambda e: None)}, "Increment"),
        )
