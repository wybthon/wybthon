from wybthon import Suspense, button, code, component, create_resource, div, h, h2, h3, on_cleanup, p, pre


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

    def render():
        text = str(res.error.get()) if res.error.get() else res.data.get() or "No data"

        return div(
            div(
                h2("Data Fetching"),
                p("Fetch data with create_resource and display loading states with Suspense."),
                class_name="page-header",
            ),
            div(
                h3("JSONPlaceholder API"),
                h(
                    Suspense,
                    {
                        "resource": res,
                        "fallback": p("Loading..."),
                        "keep_previous": True,
                        "children": [p(text)],
                    },
                ),
                div(
                    button("Reload", on_click=lambda e: res.reload()),
                    button("Cancel", on_click=lambda e: res.cancel()),
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
                        "res = create_resource(fetcher)\n"
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

    return render
