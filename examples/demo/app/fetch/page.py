from wybthon import Component, h, use_resource


class FetchPage(Component):
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
        status_text = (
            "Loading..."
            if self.res.loading.get()
            else (str(self.res.error.get()) if self.res.error.get() else self.res.data.get() or "No data")
        )
        return h(
            "div",
            {},
            h("h3", {}, "Async Fetch Demo"),
            h("p", {}, status_text),
            h("button", {"on_click": getattr(self, "_on_reload", lambda e: None)}, "Reload"),
            h("button", {"on_click": getattr(self, "_on_cancel", lambda e: None)}, "Cancel"),
        )
