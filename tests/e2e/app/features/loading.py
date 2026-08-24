"""Loading boundary: fallback while an async memo loads, then children.

The fetch is gated on an ``asyncio.Event`` so the test controls exactly
when loading resolves, making the fallback -> content transition
deterministic. A reload bumps a version signal; the revalidating memo
serves its stale value so content stays visible (no fallback).
"""

import asyncio

from app.testkit import tid

from wybthon import Loading, button, component, create_memo, create_signal, div, dynamic, h2, span


@component
def Page():
    gate = asyncio.Event()
    attempts = [0]
    version, set_version = create_signal(0)

    async def fetch_payload():
        version()  # reload dependency
        attempts[0] += 1
        await gate.wait()
        return f"payload-{attempts[0]}"

    res = create_memo(fetch_payload)

    def resolve(_e):
        gate.set()

    def reload(_e):
        gate.clear()
        set_version(version() + 1)

    return div(
        h2("Loading"),
        Loading(
            fallback=lambda: span("loading", **tid("load-fallback")),
            children=lambda: span(dynamic(lambda: res() or ""), **tid("load-content")),
        ),
        button("resolve", on_click=resolve, **tid("load-resolve")),
        button("reload", on_click=reload, **tid("load-reload")),
        **tid("page-loading"),
    )
