"""A complete edit, reorder, async filter, optimistic save, and disposal flow."""

import asyncio

from app.testkit import tid

from wybthon import (
    Errored,
    For,
    Loading,
    action,
    button,
    component,
    create_memo,
    create_optimistic_store,
    create_signal,
    create_store,
    div,
    is_pending,
    on_cleanup,
    p,
)

mounted = 0
removed = 0
cancelled = 0


@component
def Page(**rest):
    rows, edit = create_store([{"id": 1, "name": "Ada"}, {"id": 2, "name": "Grace"}])
    query, set_query = create_signal("")
    mode, set_mode = create_signal("ok")
    base, set_base = create_signal({"saved": 0})
    optimistic, set_optimistic = create_optimistic_store(base)

    async def filtered():
        value, state = query(), mode()
        if value or state != "ok":
            await asyncio.sleep(0.15)
        if state == "error":
            raise ValueError("Filter failed")
        return [row for row in rows if value.lower() in row.name.lower()]

    visible = create_memo(filtered)

    @action
    async def save():
        set_optimistic(lambda draft: setattr(draft, "saved", draft.saved + 1))
        await asyncio.sleep(0.15)
        set_base({"saved": base()["saved"] + 1})

    async def waiting(event):
        global cancelled
        try:
            await asyncio.sleep(60)
        finally:
            cancelled += 1

    def row(item, index):
        global mounted
        mounted += 1

        def dispose():
            global removed
            removed += 1

        on_cleanup(dispose)
        return div(lambda: f"{index()}:{item.name}", data_row=item.id)

    return div(
        button("Edit", on_click=lambda e: edit(lambda d: setattr(d[0], "name", "Augusta")), **tid("contract-edit")),
        button("Reverse", on_click=lambda e: edit(lambda d: d.reverse()), **tid("contract-reverse")),
        button("Filter", on_click=lambda e: set_query("Augusta"), **tid("contract-filter")),
        button("Error", on_click=lambda e: set_mode("error"), **tid("contract-error")),
        button("Recover", on_click=lambda e: set_mode("ok"), **tid("contract-recover")),
        button("Save", on_click=lambda e: save(), **tid("contract-save")),
        button("Wait", on_click=waiting, **tid("contract-wait")),
        p(lambda: str(is_pending(visible)), **tid("contract-pending")),
        p(lambda: str(optimistic.saved), **tid("contract-saved")),
        p(lambda: str(save.pending()), **tid("contract-saving")),
        Errored(
            lambda: Loading(lambda: For(visible, row), fallback="Waiting"),
            fallback=lambda error: p(str(error), **tid("contract-failure")),
        ),
        **tid("page-contracts"),
    )
