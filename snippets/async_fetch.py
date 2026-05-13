"""Async fetch with Suspense — data fetching that just works.

Tweet caption:
    Data fetching in Python. `create_resource` wraps the async call,
    `Suspense` shows a fallback until it resolves. Reload, cancel,
    error states — all built in.

Why it's interesting:
    No `useEffect`, no loading flag, no race-condition guard. The
    resource exposes `data`, `error`, and `loading` as signals. Pass
    an `AbortSignal` straight through to `fetch` for cancellation.
"""

from wybthon import (
    Suspense,
    button,
    component,
    create_resource,
    div,
    dynamic,
    h,
    on_cleanup,
    p,
)


@component
def TodoFetcher():
    async def load(signal=None):
        from js import fetch

        resp = await fetch("https://jsonplaceholder.typicode.com/todos/1", {"signal": signal})
        data = await resp.json()
        return str(data.title)

    res = create_resource(load)
    on_cleanup(lambda: res.cancel())

    def view():
        return res.error.get() or res.data.get() or "(no data yet)"

    return div(
        h(Suspense, {"resource": res, "fallback": p("Loading...")}, p(dynamic(view))),
        button("Reload", on_click=lambda e: res.reload()),
        button("Cancel", on_click=lambda e: res.cancel()),
    )
