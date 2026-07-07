from wybthon import Suspense, button, code, component, create_resource, div, dynamic, h2, h3, on_cleanup, p, pre


@component
def FetchPage():
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

    res = create_resource(fetcher)

    on_cleanup(lambda: res.cancel())

    def display_text() -> str:
        if res.error:
            return str(res.error)
        return res() or "No data"

    return div(
        div(
            h2("Data Fetching"),
            p("Fetch data with create_resource and display loading states with Suspense."),
            class_="page-header",
        ),
        div(
            h3("JSONPlaceholder API"),
            Suspense(
                fallback=p("Loading..."),
                children=lambda: p(dynamic(display_text)),
            ),
            div(
                button("Refetch", on_click=lambda e: res.refetch()),
                button("Cancel", on_click=lambda e: res.cancel()),
            ),
            class_="demo-section",
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
                    "res = create_resource(fetcher)\n"
                    "\n"
                    "Suspense(\n"
                    '    fallback=p("Loading..."),\n'
                    '    children=lambda: p(dynamic(lambda: res() or "")),\n'
                    ")"
                ),
                class_="code-block",
            ),
            class_="demo-section",
        ),
        class_="page",
    )
