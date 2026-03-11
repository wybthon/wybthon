from wybthon import Component, Suspense, button, code, div, h, h2, h3, p, pre, use_resource


class FetchPage(Component):
    def __init__(self, props):
        super().__init__(props)

        async def fetcher(signal=None):
            import importlib

            js = importlib.import_module("js")
            if signal is not None:
                resp = await js.fetch(
                    "https://jsonplaceholder.typicode.com/todos/1", {"signal": signal}
                )
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
        def content(_props):
            text = (
                str(self.res.error.get())
                if self.res.error.get()
                else self.res.data.get() or "No data"
            )
            return p(text)

        return div(
            div(
                h2("Data Fetching"),
                p(
                    "Fetch data with use_resource and display loading states "
                    "with Suspense."
                ),
                class_name="page-header",
            ),
            div(
                h3("JSONPlaceholder API"),
                h(
                    Suspense,
                    {
                        "resource": self.res,
                        "fallback": p("Loading..."),
                        "keep_previous": True,
                    },
                    content({}),
                ),
                div(
                    button(
                        "Reload",
                        on_click=getattr(self, "_on_reload", lambda e: None),
                    ),
                    button(
                        "Cancel",
                        on_click=getattr(self, "_on_cancel", lambda e: None),
                    ),
                ),
                class_name="demo-section",
            ),
            div(
                h3("How It Works"),
                pre(
                    code(
                        "async def fetcher(signal=None):\n"
                        '    resp = await js.fetch(url, {"signal": signal})\n'
                        "    data = await resp.json()\n"
                        '    return f"Todo: {data.title}"\n'
                        "\n"
                        "res = use_resource(fetcher)\n"
                        "\n"
                        "h(Suspense, {\n"
                        '    "resource": res,\n'
                        '    "fallback": p("Loading..."),\n'
                        "}, content)"
                    ),
                    class_name="code-block",
                ),
                class_name="demo-section",
            ),
            class_name="page",
        )
