"""Suspense: fallback while a resource loads, then children once resolved.

The fetch is gated on an ``asyncio.Event`` so the test controls exactly when
loading resolves, making the fallback -> content transition deterministic.
"""

import asyncio

from app.testkit import tid

from wybthon import Suspense, button, component, create_resource, div, dynamic, h2, span


@component
def Page():
    gate = asyncio.Event()
    attempts = [0]

    async def fetcher(signal=None):
        attempts[0] += 1
        await gate.wait()
        return f"payload-{attempts[0]}"

    res = create_resource(fetcher)

    def resolve(_e):
        gate.set()

    def reload(_e):
        gate.clear()
        res.refetch()

    return div(
        h2("Suspense"),
        Suspense(
            fallback=lambda: span("loading", **tid("susp-fallback")),
            children=lambda: span(dynamic(lambda: res() or ""), **tid("susp-content")),
        ),
        button("resolve", on_click=resolve, **tid("susp-resolve")),
        button("reload", on_click=reload, **tid("susp-reload")),
        **tid("page-suspense"),
    )
