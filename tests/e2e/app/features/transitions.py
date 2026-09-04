"""Transitions: held updates, ``is_pending``, actions with optimistic values.

Changing the selected id makes an async memo pending. The header that
reads the id and the body that reads the async result are held together
on the old state until the fetch resolves, while an ``is_pending`` probe
drives an inline indicator. A gated action shows an optimistic value
that reverts when the real write lands. A sequential ``Reveal`` orders
two boundaries top to bottom.
"""

import asyncio

from app.testkit import tid

from wybthon import (
    Loading,
    Reveal,
    action,
    button,
    component,
    create_memo,
    create_optimistic,
    create_signal,
    div,
    h2,
    is_pending,
    p,
    span,
)


@component
def Page(**rest):
    uid, set_uid = create_signal(1)
    gates = {1: asyncio.Event(), 2: asyncio.Event()}
    gates[1].set()

    async def load_user():
        i = uid()
        await gates[i].wait()
        return f"user{i}"

    user = create_memo(load_user)

    # -- action + optimistic value ------------------------------------------
    saved, set_saved = create_signal("none")
    shown, set_shown = create_optimistic(saved)
    save_gate = asyncio.Event()

    @action
    async def save(value):
        set_shown(f"{value} (saving)")
        await save_gate.wait()
        set_saved(value)

    # -- sequential reveal -----------------------------------------------------
    ra, rb = asyncio.Event(), asyncio.Event()

    async def load_a():
        await ra.wait()
        return "A"

    async def load_b():
        await rb.wait()
        return "B"

    ma = create_memo(load_a)
    mb = create_memo(load_b)

    return div(
        h2("Transitions"),
        p("id: ", span(lambda: f"id={uid()}", **tid("tx-head"))),
        p("user: ", span(user, **tid("tx-body"))),
        p("state: ", span(lambda: "pending" if is_pending(uid) else "idle", **tid("tx-state"))),
        button("select 2", on_click=lambda e: set_uid(2), **tid("tx-select")),
        button("resolve user", on_click=lambda e: gates[2].set(), **tid("tx-resolve")),
        p("saved: ", span(shown, **tid("tx-saved"))),
        p("saving: ", span(lambda: "yes" if save.pending() else "no", **tid("tx-saving"))),
        button("save", on_click=lambda e: save("done"), **tid("tx-save")),
        button("finish save", on_click=lambda e: save_gate.set(), **tid("tx-finish")),
        div(
            Reveal(
                [
                    Loading(lambda: span(ma, **tid("tx-a")), fallback=lambda: span("fa", **tid("tx-fa"))),
                    Loading(lambda: span(mb, **tid("tx-b")), fallback=lambda: span("fb", **tid("tx-fb"))),
                ],
            ),
            **tid("tx-reveal"),
        ),
        button("resolve b", on_click=lambda e: rb.set(), **tid("tx-resolve-b")),
        button("resolve a", on_click=lambda e: ra.set(), **tid("tx-resolve-a")),
        **tid("page-transitions"),
    )
