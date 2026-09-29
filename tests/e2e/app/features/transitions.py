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
        ConcurrentPanel(),
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


@component
def ConcurrentPanel():
    """Gated requests and optimistic edits exercise publication across the bridge."""
    from wybthon import create_optimistic_store, deep, input_, latest

    def resource():
        selected, select = create_signal(0)
        gate = asyncio.Event()

        async def load():
            value = selected()
            if value:
                await gate.wait()
            return f"data{value}"

        return selected, select, create_memo(load), gate

    left, select_left, left_data, left_gate = resource()
    right, select_right, right_data, right_gate = resource()
    text, set_text = create_signal("")
    shown, edit = create_optimistic_store({"count": 0})
    first, second = asyncio.Event(), asyncio.Event()

    @action
    async def add(amount, gate):
        edit(lambda draft: draft.update(count=draft.count + amount))
        await gate.wait()

    return div(
        span(left, **tid("ind-left-id")),
        span(left_data, **tid("ind-left-data")),
        span(lambda: latest(left), **tid("ind-left-latest")),
        span(right, **tid("ind-right-id")),
        span(right_data, **tid("ind-right-data")),
        input_(value=text, on_input=lambda event: set_text(str(event.target.value)), **tid("ind-input")),
        span(text, **tid("ind-echo")),
        button("start both", on_click=lambda event: (select_left(1), select_right(1)), **tid("ind-start")),
        button("finish left", on_click=lambda event: left_gate.set(), **tid("ind-finish-left")),
        button("finish right", on_click=lambda event: right_gate.set(), **tid("ind-finish-right")),
        span(lambda: str(deep(shown)["count"]), **tid("ind-optimistic")),
        button("add one", on_click=lambda event: add(1, first), **tid("ind-add-one")),
        button("add ten", on_click=lambda event: add(10, second), **tid("ind-add-ten")),
        button("finish ten", on_click=lambda event: second.set(), **tid("ind-finish-ten")),
        button("finish one", on_click=lambda event: first.set(), **tid("ind-finish-one")),
    )
