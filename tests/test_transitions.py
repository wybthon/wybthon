"""Transitions: consistent reveals across async recomputes and actions."""

from __future__ import annotations

import asyncio

import pytest
from conftest import StubNode, collect_texts

from wybthon.component import component
from wybthon.error_boundary import Errored
from wybthon.html import div, p, span
from wybthon.loading import Loading
from wybthon.reactivity import (
    Memo,
    NotReadyError,
    Setter,
    action,
    affects,
    create_effect,
    create_memo,
    create_optimistic,
    create_root,
    create_signal,
    flush,
    is_pending,
    latest,
    refresh,
    until,
)
from wybthon.store import create_optimistic_store, create_projection, create_store, deep


def texts(node: StubNode) -> list[str]:
    return [t for t in collect_texts(node) if t]


async def _tick(n: int = 3) -> None:
    for _ in range(n):
        flush()
        await asyncio.sleep(0)
    flush()


def _user_app(wyb, root_element):
    """A header showing the selected id and a body showing the loaded user."""
    uid, set_uid = create_signal(1)
    gates = {1: asyncio.Event(), 2: asyncio.Event(), 3: asyncio.Event()}

    async def load():
        i = uid()
        await gates[i].wait()
        return f"user{i}"

    @component
    def App():
        user = create_memo(load)
        return div(
            span(lambda: f"id={uid()}"),
            Loading(lambda: p(user), fallback=p("wait")),
            span(lambda: "pending" if is_pending(user) else "idle"),
        )

    wyb["reconciler"].render(App(), root_element)
    return uid, set_uid, gates


# ---------------------------------------------------------------------------
# Holding and revealing
# ---------------------------------------------------------------------------


def test_input_change_and_async_result_reveal_together(wyb, root_element):
    async def main() -> None:
        uid, set_uid, gates = _user_app(wyb, root_element)
        gates[1].set()
        await _tick()
        assert texts(root_element.element) == ["id=1", "user1", "idle"]

        set_uid(2)
        await _tick()
        # The header does not tear ahead of the body: both hold on the old
        # state while the pending indicator shows.
        assert texts(root_element.element) == ["id=1", "user1", "pending"]
        gates[2].set()
        await _tick()
        assert texts(root_element.element) == ["id=2", "user2", "idle"]

    asyncio.run(main())


def test_reads_outside_the_graph_see_revealed_state_and_latest_sees_new(wyb, root_element):
    async def main() -> None:
        uid, set_uid, gates = _user_app(wyb, root_element)
        gates[1].set()
        await _tick()
        set_uid(2)
        await _tick()
        assert uid() == 1  # what the UI shows
        assert uid.peek() == 1
        assert latest(uid) == 2  # what's coming
        assert is_pending(uid)
        # Functional updates compose on the newest value.
        set_uid(lambda n: n + 1)
        await _tick()
        assert latest(uid) == 3
        gates[3].set()
        await _tick()
        assert uid() == 3
        assert not is_pending(uid)
        assert texts(root_element.element) == ["id=3", "user3", "idle"]

    asyncio.run(main())


def test_unrelated_writes_reveal_while_a_transition_is_held(wyb, root_element):
    async def main() -> None:
        text, set_text = create_signal("a")
        uid, set_uid = create_signal(1)
        gates = {1: asyncio.Event(), 2: asyncio.Event()}

        async def load():
            i = uid()
            await gates[i].wait()
            return f"user{i}"

        user = create_root(lambda d: create_memo(load))
        wyb["reconciler"].render(div(span(text), span(lambda: str(uid())), p(user)), root_element)
        gates[1].set()
        await _tick()
        set_uid(2)
        await _tick()
        set_text("b")
        await _tick()
        # Typing is independent of the pending navigation.
        assert texts(root_element.element) == ["b", "1", "user1"]
        gates[2].set()
        await _tick()
        assert texts(root_element.element) == ["b", "2", "user2"]

    asyncio.run(main())


def test_derived_memos_and_effects_are_held_with_their_inputs(wyb):
    async def main() -> None:
        uid, set_uid = create_signal(1)
        label = create_root(lambda d: create_memo(lambda: f"#{uid()}"))
        gates = {1: asyncio.Event(), 2: asyncio.Event()}

        async def load():
            i = uid()
            await gates[i].wait()
            return i * 10

        data = create_root(lambda d: create_memo(load))
        seen: list[tuple[str, int]] = []
        create_root(lambda d: create_effect(lambda: (label(), data()), seen.append))
        gates[1].set()
        await _tick()
        assert seen == [("#1", 10)]
        set_uid(2)
        await _tick()
        assert label() == "#1"  # revealed view
        assert latest(label) == "#2"
        assert seen == [("#1", 10)]  # the effect never observes a torn pair
        gates[2].set()
        await _tick()
        assert seen == [("#1", 10), ("#2", 20)]

    asyncio.run(main())


def test_first_load_shows_fallback_and_does_not_hold(wyb, root_element):
    async def main() -> None:
        show, set_show = create_signal(False)
        gate = asyncio.Event()

        async def load():
            await gate.wait()
            return "data"

        @component
        def Panel():
            data = create_memo(load)
            return Loading(lambda: p(data), fallback=p("wait"))

        wyb["reconciler"].render(
            div(span(lambda: "on" if show() else "off"), lambda: Panel() if show() else None), root_element
        )
        flush()
        set_show(True)
        await _tick()
        # A newly mounted branch is branch readiness: fallback, no hold.
        assert texts(root_element.element) == ["on", "wait"]
        gate.set()
        await _tick()
        assert texts(root_element.element) == ["on", "data"]

    asyncio.run(main())


def test_loading_value_never_suspends_or_holds(wyb, root_element):
    async def main() -> None:
        uid, set_uid = create_signal(1)
        gates = {1: asyncio.Event(), 2: asyncio.Event()}

        async def load():
            i = uid()
            await gates[i].wait()
            return [f"tip{i}"]

        tips: Memo[list[str]] = create_root(lambda d: create_memo(load, loading_value=[]))
        assert tips() == []
        assert not is_pending(tips)
        wyb["reconciler"].render(div(span(lambda: str(uid())), p(lambda: ",".join(tips()))), root_element)
        flush()
        assert texts(root_element.element) == ["1"]
        gates[1].set()
        await _tick()
        assert texts(root_element.element) == ["1", "tip1"]
        set_uid(2)
        await _tick()
        # The recompute is a real pending change now, so it entangles like any other.
        assert is_pending(tips)
        gates[2].set()
        await _tick()
        assert texts(root_element.element) == ["2", "tip2"]

    asyncio.run(main())


def test_loading_on_shows_fallback_again_instead_of_holding(wyb, root_element):
    async def main() -> None:
        uid, set_uid = create_signal(1)
        gates = {1: asyncio.Event(), 2: asyncio.Event()}

        async def load():
            i = uid()
            await gates[i].wait()
            return f"user{i}"

        @component
        def Card():
            user = create_memo(load)
            return p(user)

        wyb["reconciler"].render(
            div(span(lambda: str(uid())), Loading(lambda: Card(), fallback=p("wait"), on=uid)), root_element
        )
        gates[1].set()
        await _tick()
        assert texts(root_element.element) == ["1", "user1"]
        set_uid(2)
        await _tick()
        # New record: the header moves on and the boundary shows its fallback.
        assert texts(root_element.element) == ["2", "wait"]
        gates[2].set()
        await _tick()
        assert texts(root_element.element) == ["2", "user2"]

    asyncio.run(main())


def test_quiet_refresh_does_not_open_a_transition(wyb, root_element):
    async def main() -> None:
        calls: list[int] = []

        async def load():
            calls.append(1)
            await asyncio.sleep(0)
            return len(calls)

        n = create_root(lambda d: create_memo(load))
        wyb["reconciler"].render(div(p(n), span(lambda: "p" if is_pending(n) else "i")), root_element)
        await _tick()
        assert texts(root_element.element) == ["1", "i"]
        await refresh(n)
        await _tick()
        assert texts(root_element.element) == ["2", "i"]

    asyncio.run(main())


# ---------------------------------------------------------------------------
# Actions as transactions
# ---------------------------------------------------------------------------


def test_action_writes_land_together_when_it_settles(wyb, root_element):
    async def main() -> None:
        status, set_status = create_signal("idle")
        count, set_count = create_signal(0)
        gate = asyncio.Event()

        @action
        async def save():
            set_status("saving")
            await gate.wait()
            set_count(1)
            set_status("saved")

        wyb["reconciler"].render(div(span(status), span(lambda: str(count()))), root_element)
        flush()
        fut = save()
        await _tick()
        # Plain writes inside the action are truth-in-progress: held.
        assert texts(root_element.element) == ["idle", "0"]
        assert status() == "idle"
        assert latest(status) == "saving"
        assert is_pending(status)
        assert save.pending() is True
        gate.set()
        await fut
        await _tick()
        assert texts(root_element.element) == ["saved", "1"]
        assert not is_pending(status)
        assert save.pending() is False

    asyncio.run(main())


def test_optimistic_state_reveals_during_the_action(wyb, root_element):
    async def main() -> None:
        likes, set_likes = create_signal(1)
        shown, set_shown = create_optimistic(likes)
        saving, set_saving = create_optimistic(False)
        gate = asyncio.Event()

        @action
        async def like():
            set_shown(lambda n: n + 1)
            set_saving(True)
            await gate.wait()
            set_likes(2)

        wyb["reconciler"].render(
            div(span(lambda: str(shown())), span(lambda: "saving" if saving() else "ready")), root_element
        )
        flush()
        fut = like()
        await _tick()
        assert texts(root_element.element) == ["2", "saving"]
        assert is_pending(shown)
        gate.set()
        await fut
        await _tick()
        assert texts(root_element.element) == ["2", "ready"]
        assert likes() == 2
        assert not is_pending(shown)

    asyncio.run(main())


def test_sync_action_reveals_in_the_same_flush(wyb):
    count, set_count = create_signal(0)

    @action
    def bump():
        set_count(lambda n: n + 1)
        return "ok"

    assert bump() == "ok"
    flush()
    assert count() == 1
    assert not is_pending(count)


def test_refresh_inside_action_lands_with_the_transaction(wyb):
    async def main() -> None:
        server = {"n": 1}

        async def load():
            await asyncio.sleep(0)
            return server["n"]

        n = create_root(lambda d: create_memo(load))
        seen: list[int] = []
        create_root(lambda d: create_effect(n, seen.append))
        await _tick()
        assert seen == [1]
        gate = asyncio.Event()

        @action
        async def bump():
            server["n"] = 2
            await refresh(n)
            await gate.wait()

        fut = bump()
        await _tick(6)
        # The refreshed value has landed in the graph but waits for the action.
        assert latest(n) == 2
        assert n() == 1
        assert seen == [1]
        gate.set()
        await fut
        await _tick()
        assert n() == 2
        assert seen == [1, 2]

    asyncio.run(main())


def test_affects_marks_targets_pending_until_settle(wyb):
    async def main() -> None:
        users, set_users = create_signal(["a"])
        gate = asyncio.Event()

        @action
        async def rename():
            affects(users)
            await gate.wait()
            set_users(["b"])

        assert not is_pending(users)
        fut = rename()
        flush()
        assert is_pending(users)
        gate.set()
        await fut
        await _tick()
        assert not is_pending(users)
        assert users() == ["b"]

    asyncio.run(main())


def test_affects_outside_action_raises(wyb):
    count, _ = create_signal(0)
    with pytest.raises(RuntimeError):
        affects(count)
    with pytest.raises(TypeError):

        @action
        def bad():
            affects(42)

        bad()


def test_until_waits_for_authoritative_truth(wyb):
    async def main() -> None:
        saved, set_saved = create_signal(False)
        shown, set_shown = create_optimistic(saved)
        order: list[str] = []

        @action
        async def save():
            set_shown(True)  # optimistic: invisible to until()
            order.append("optimistic")

            async def later():
                await asyncio.sleep(0)
                await asyncio.sleep(0)
                set_saved(True)
                order.append("truth")

            asyncio.ensure_future(later())
            await until(shown)
            order.append("done")

        await save()
        assert order == ["optimistic", "truth", "done"]

    asyncio.run(main())


def test_until_timeout(wyb):
    async def main() -> None:
        never, _ = create_signal(False)
        with pytest.raises(TimeoutError):
            await until(never, timeout=0.01)

    asyncio.run(main())


def test_until_ignores_not_ready(wyb):
    async def main() -> None:
        gate = asyncio.Event()

        async def load():
            await gate.wait()
            return True

        ready = create_root(lambda d: create_memo(load))

        async def wait_ready() -> str:
            await until(ready)
            return "ready"

        task = asyncio.ensure_future(wait_ready())
        await asyncio.sleep(0)
        assert not task.done()
        gate.set()
        assert await task == "ready"

    asyncio.run(main())


# ---------------------------------------------------------------------------
# Error boundaries heal
# ---------------------------------------------------------------------------


def test_errored_heals_when_a_failed_input_changes(wyb, root_element):
    boom, set_boom = create_signal(True)
    resets: list = []

    def risky():
        if boom():
            raise ValueError("bad")
        return "fine"

    wyb["reconciler"].render(
        Errored(lambda: p(risky), fallback=lambda err, reset: (resets.append(reset), p("oops"))[1]), root_element
    )
    flush()
    assert texts(root_element.element) == ["oops"]
    set_boom(False)
    flush()
    # No reset() call: the input the failing hole read changed.
    assert texts(root_element.element) == ["fine"]
    set_boom(True)
    flush()
    assert texts(root_element.element) == ["oops"]


def test_errored_heals_when_failed_memo_recovers(wyb, root_element):
    async def main() -> None:
        attempt, set_attempt = create_signal(1)

        async def load():
            n = attempt()
            await asyncio.sleep(0)
            if n == 1:
                raise RuntimeError("fetch failed")
            return f"ok{n}"

        @component
        def Card():
            data = create_memo(load)
            return p(data)

        wyb["reconciler"].render(
            Errored(lambda: Loading(lambda: Card(), fallback=p("wait")), fallback=lambda e: p(str(e))), root_element
        )
        await _tick()
        assert texts(root_element.element) == ["fetch failed"]
        set_attempt(2)
        await _tick()
        assert texts(root_element.element) == ["ok2"]

    asyncio.run(main())


def test_not_ready_error_still_raised_outside_latest(wyb):
    async def main() -> None:
        gate = asyncio.Event()

        async def load():
            await gate.wait()
            return 1

        m = create_root(lambda d: create_memo(load))
        with pytest.raises(NotReadyError):
            m()
        assert latest(m) is None
        gate.set()
        await _tick()
        assert m() == 1

    asyncio.run(main())


# ---------------------------------------------------------------------------
# Stores
# ---------------------------------------------------------------------------


def test_projection_is_held_with_its_inputs(wyb, root_element):
    async def main() -> None:
        uid, set_uid = create_signal(1)
        gates = {1: asyncio.Event(), 2: asyncio.Event()}

        async def load():
            i = uid()
            await gates[i].wait()
            return f"user{i}"

        user = create_root(lambda d: create_memo(load))
        view = create_root(lambda d: create_projection(lambda draft: draft.update({"label": f"#{uid()}"}), {}))
        wyb["reconciler"].render(div(span(lambda: view.label), p(user)), root_element)
        gates[1].set()
        await _tick()
        assert texts(root_element.element) == ["#1", "user1"]
        set_uid(2)
        await _tick()
        assert texts(root_element.element) == ["#1", "user1"]
        assert view.label == "#1"
        assert latest(lambda: view.label) == "#2"
        gates[2].set()
        await _tick()
        assert texts(root_element.element) == ["#2", "user2"]

    asyncio.run(main())


def test_optimistic_store_reveals_inside_action_and_reports_pending(wyb, root_element):
    async def main() -> None:
        todos, set_todos = create_store({"items": []})
        shown, set_shown = create_optimistic_store(lambda: deep(todos)["items"], [])
        gate = asyncio.Event()

        @action
        async def add(title: str):
            set_shown(lambda s: s.append({"title": title}))
            await gate.wait()
            set_todos(lambda s: s.items.append({"title": title}))

        wyb["reconciler"].render(
            div(
                span(lambda: str(len(shown))),
                span(lambda: "saving" if is_pending(lambda: len(shown)) else "idle"),
                span(lambda: str(len(todos.items))),
            ),
            root_element,
        )
        flush()
        assert texts(root_element.element) == ["0", "idle", "0"]
        fut = add("a")
        await _tick()
        # The overlay shows now; the store write waits for the action.
        assert texts(root_element.element) == ["1", "saving", "0"]
        gate.set()
        await fut
        await _tick()
        assert texts(root_element.element) == ["1", "idle", "1"]

    asyncio.run(main())


def test_affects_store_marks_reads_pending(wyb):
    async def main() -> None:
        users, set_users = create_store({"items": [{"id": 1, "name": "a"}]})
        gate = asyncio.Event()

        @action
        async def rename():
            affects(users)
            await gate.wait()
            set_users(lambda s: s.items[0].update({"name": "b"}))

        assert not is_pending(lambda: users.items[0].name)
        fut = rename()
        flush()
        assert is_pending(lambda: users.items[0].name)
        gate.set()
        await fut
        await _tick()
        assert not is_pending(lambda: users.items[0].name)
        assert users.items[0].name == "b"

    asyncio.run(main())


def test_setter_type_is_exported() -> None:
    assert Setter is not None
