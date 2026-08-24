from wybthon import (
    Loading,
    button,
    code,
    component,
    create_memo,
    create_signal,
    div,
    dynamic,
    h2,
    h3,
    is_pending,
    p,
    pre,
    span,
)


@component
def FetchPage():
    version, set_version = create_signal(0)

    async def fetch_todo():
        version()  # refetch dependency
        import importlib

        js = importlib.import_module("js")
        resp = await js.fetch("https://jsonplaceholder.typicode.com/todos/1")
        data = await resp.json()
        title = str(getattr(data, "title", "unknown"))
        return f"Todo: {title}"

    todo = create_memo(fetch_todo)

    return div(
        div(
            h2("Data Fetching"),
            p("Fetch data with an async create_memo and display loading states with Loading."),
            class_="page-header",
        ),
        div(
            h3("JSONPlaceholder API"),
            Loading(
                fallback=p("Loading..."),
                children=lambda: p(dynamic(lambda: todo() or "No data")),
            ),
            p(
                "Refreshing: ",
                span(dynamic(lambda: "yes" if is_pending(todo) else "no")),
                style={"color": "var(--text-3)"},
            ),
            div(
                button("Refetch", on_click=lambda e: set_version(version() + 1)),
            ),
            class_="demo-section",
        ),
        div(
            h3("How It Works"),
            pre(
                code(
                    "async def fetch_todo():\n"
                    "    version()  # refetch dependency\n"
                    "    resp = await js.fetch(url)\n"
                    "    data = await resp.json()\n"
                    '    return f"Todo: {data.title}"\n'
                    "\n"
                    "todo = create_memo(fetch_todo)\n"
                    "\n"
                    "Loading(\n"
                    '    fallback=p("Loading..."),\n'
                    "    children=lambda: p(dynamic(todo)),\n"
                    ")"
                ),
                class_="code-block",
            ),
            p(
                "Reads of a pending async memo raise NotReadyError, which the "
                "nearest Loading boundary catches to show its fallback. A "
                "refetch serves the previous value while the new one loads "
                "(stale-while-revalidate); is_pending() reports the refresh."
            ),
            class_="demo-section",
        ),
        class_="page",
    )
