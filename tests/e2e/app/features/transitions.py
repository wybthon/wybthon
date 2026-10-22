"""Transitions: held updates, ``is_pending``, actions with optimistic values.

Changing the selected id makes an async memo pending. The header that
reads the id and the body that reads the async result are held together
on the old state until the fetch resolves, while an ``is_pending`` probe
drives an inline indicator. A gated action shows an optimistic value
that reverts when the real write lands. A sequential ``Reveal`` orders
two boundaries top to bottom.
"""

import asyncio

from wybthon import (
    Loading,
    Reveal,
    action,
    component,
    create_memo,
    create_optimistic,
    create_optimistic_store,
    create_signal,
    deep,
    html,
    is_pending,
    latest,
)


@component
def Page():
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

    return html(t"""
      <div data-testid="page-transitions">
        <h2>Transitions</h2>
        <{ConcurrentPanel} />
        <p>id: <span data-testid="tx-head">id={uid()}</span></p>
        <p>user: <span data-testid="tx-body">{user()}</span></p>
        <p>state: <span data-testid="tx-state">{"pending" if is_pending(uid) else "idle"}</span></p>
        <button data-testid="tx-select" onclick={(lambda e: set_uid(2))}>select 2</button>
        <button data-testid="tx-resolve" onclick={(lambda e: gates[2].set())}>resolve user</button>
        <p>saved: <span data-testid="tx-saved">{shown()}</span></p>
        <p>saving: <span data-testid="tx-saving">{"yes" if save.pending() else "no"}</span></p>
        <button data-testid="tx-save" onclick={(lambda e: save("done"))}>save</button>
        <button data-testid="tx-finish" onclick={(lambda e: save_gate.set())}>finish save</button>
        <div data-testid="tx-reveal">
          <{Reveal}>
            {
        Loading(
            html(t'<span data-testid="tx-a">{ma()}</span>'),
            fallback=html(t'<span data-testid="tx-fa">fa</span>'),
        )
    }
            {
        Loading(
            html(t'<span data-testid="tx-b">{mb()}</span>'),
            fallback=html(t'<span data-testid="tx-fb">fb</span>'),
        )
    }
          </{Reveal}>
        </div>
        <button data-testid="tx-resolve-b" onclick={(lambda e: rb.set())}>resolve b</button>
        <button data-testid="tx-resolve-a" onclick={(lambda e: ra.set())}>resolve a</button>
      </div>
    """)


@component
def ConcurrentPanel():
    """Gated requests and optimistic edits exercise publication across the bridge."""

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

    return html(t"""
      <div>
        <span data-testid="ind-left-id">{left()}</span>
        <span data-testid="ind-left-data">{left_data()}</span>
        <span data-testid="ind-left-latest">{latest(left)}</span>
        <span data-testid="ind-right-id">{right()}</span>
        <span data-testid="ind-right-data">{right_data()}</span>
        <input data-testid="ind-input" value={text()} oninput={(lambda event: set_text(str(event.target.value)))}>
        <span data-testid="ind-echo">{text()}</span>
        <button data-testid="ind-start" onclick={(lambda event: (select_left(1), select_right(1)))}>start both</button>
        <button data-testid="ind-finish-left" onclick={(lambda event: left_gate.set())}>finish left</button>
        <button data-testid="ind-finish-right" onclick={(lambda event: right_gate.set())}>finish right</button>
        <span data-testid="ind-optimistic">{str(deep(shown)["count"])}</span>
        <button data-testid="ind-add-one" onclick={(lambda event: add(1, first))}>add one</button>
        <button data-testid="ind-add-ten" onclick={(lambda event: add(10, second))}>add ten</button>
        <button data-testid="ind-finish-ten" onclick={(lambda event: second.set())}>finish ten</button>
        <button data-testid="ind-finish-one" onclick={(lambda event: first.set())}>finish one</button>
      </div>
    """)
