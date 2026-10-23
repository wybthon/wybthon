"""Loading boundary: fallback while an async memo loads, then children.

The fetch is gated on an ``asyncio.Event`` so the test controls exactly
when loading resolves, making the fallback -> content transition
deterministic. A reload bumps a version signal; the revalidating memo
serves its stale value so content stays visible (no fallback).
"""

import asyncio

from wybthon import Loading, component, create_memo, create_signal, html


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
        set_version(lambda v: v + 1)

    # The content's `{res() or ""}` hole reads the async memo inside the
    # boundary, which shows the fallback until it first resolves.
    return html(t"""
      <div data-testid="page-loading">
        <h2>Loading</h2>
        {
        Loading(
            html(t'<span data-testid="load-content">{res() or ""}</span>'),
            fallback=html(t'<span data-testid="load-fallback">loading</span>'),
        )
    }
        <button data-testid="load-resolve" onclick={resolve}>resolve</button>
        <button data-testid="load-reload" onclick={reload}>reload</button>
      </div>
    """)
