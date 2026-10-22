"""A complete edit, reorder, async filter, optimistic save, and disposal flow."""

import asyncio

from wybthon import (
    Errored,
    For,
    Loading,
    action,
    component,
    create_memo,
    create_optimistic_store,
    create_signal,
    create_store,
    html,
    is_pending,
    on_cleanup,
)

mounted = 0
removed = 0
cancelled = 0


@component
def Page():
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
        return html(t"<div data-row={item.id}>{index()}:{item.name}</div>")

    def failure(err):
        return html(t'<p data-testid="contract-failure">{str(err())}</p>')

    return html(t"""
      <div data-testid="page-contracts">
        <button data-testid="contract-edit" onclick={(lambda e: edit(lambda d: setattr(d[0], "name", "Augusta")))}>
          Edit
        </button>
        <button data-testid="contract-reverse" onclick={(lambda e: edit(lambda d: d.reverse()))}>Reverse</button>
        <button data-testid="contract-filter" onclick={(lambda e: set_query("Augusta"))}>Filter</button>
        <button data-testid="contract-error" onclick={(lambda e: set_mode("error"))}>Error</button>
        <button data-testid="contract-recover" onclick={(lambda e: set_mode("ok"))}>Recover</button>
        <button data-testid="contract-save" onclick={(lambda e: save())}>Save</button>
        <button data-testid="contract-wait" onclick={waiting}>Wait</button>
        <p data-testid="contract-pending">{str(is_pending(visible))}</p>
        <p data-testid="contract-saved">{str(optimistic.saved)}</p>
        <p data-testid="contract-saving">{str(save.pending())}</p>
        {Errored(Loading(For(visible(), row), fallback="Waiting"), fallback=failure)}
      </div>
    """)
