"""Publication contracts for independent and entangled reactive versions."""

from __future__ import annotations

import asyncio

import pytest
from conftest import collect_texts

from wybthon import (
    action,
    affects,
    create_memo,
    create_optimistic,
    create_optimistic_store,
    create_root,
    create_signal,
    create_store,
    deep,
    div,
    flush,
    is_pending,
    latest,
    p,
    refresh,
    resolve,
    span,
    until,
)
from wybthon.reactivity import _core


async def tick(n=5):
    for _ in range(n):
        flush()
        await asyncio.sleep(0)
    flush()


def texts(root):
    return [text for text in collect_texts(root.element) if text]


def loader():
    query, write = create_signal(0)
    gates = {i: asyncio.Event() for i in range(1, 5)}

    async def fetch():
        value = query()
        if value:
            await gates[value].wait()
        return str(value)

    data = create_root(lambda dispose: create_memo(fetch))
    return query, write, data, gates


@pytest.mark.parametrize("same_batch", [False, True])
def test_independent_requests_publish_independently(wyb, root_element, same_batch):
    async def main():
        left, set_left, left_data, left_gates = loader()
        right, set_right, right_data, right_gates = loader()
        wyb["reconciler"].render(div(span(left), p(left_data), span(right), p(right_data)), root_element)
        await tick()
        set_left(1)
        if not same_batch:
            await tick()
        set_right(1)
        await tick()
        assert texts(root_element) == ["0", "0", "0", "0"]
        assert len(_core._transitions) == 2
        right_gates[1].set()
        await tick()
        assert texts(root_element) == ["0", "0", "1", "1"]
        assert len(_core._transitions) == 1
        left_gates[1].set()
        await tick()
        assert texts(root_element) == ["1", "1", "1", "1"]
        assert not _core._transitions

    asyncio.run(main())


def test_shared_consumer_entangles_requests(wyb, root_element):
    async def main():
        left, set_left, left_data, lg = loader()
        right, set_right, right_data, rg = loader()
        wyb["reconciler"].render(div(span(left), span(right), p(lambda: left_data() + right_data())), root_element)
        await tick()
        set_left(1)
        set_right(1)
        await tick()
        assert len(_core._transitions) == 1
        rg[1].set()
        await tick()
        assert texts(root_element) == ["0", "0", "00"]
        lg[1].set()
        await tick()
        assert texts(root_element) == ["1", "1", "11"]

    asyncio.run(main())


def test_latest_render_edge_escapes_hold_but_ordinary_edge_wins(wyb, root_element):
    async def main():
        query, write, data, gates = loader()
        eager = create_root(lambda dispose: create_memo(lambda: latest(query)))
        wyb["reconciler"].render(
            div(span(query), span(lambda: latest(query)), span(eager), p(lambda: (latest(query), query())), p(data)),
            root_element,
        )
        await tick()
        write(1)
        await tick()
        assert texts(root_element) == ["0", "1", "1", "0", "0", "0"]
        gates[1].set()
        await tick()
        assert texts(root_element) == ["1", "1", "1", "1", "1", "1"]

    asyncio.run(main())


def test_unrendered_async_and_same_batch_typing_do_not_hold(wyb, root_element):
    async def main():
        query, write, data, gates = loader()
        typed, type_text = create_signal("a")
        wyb["reconciler"].render(div(span(query), span(typed)), root_element)
        await tick()
        write(1)
        type_text("b")
        await tick()
        assert texts(root_element) == ["1", "b"]
        assert is_pending(data)
        assert not _core._transitions
        gates[1].set()
        await tick()

    asyncio.run(main())


def test_same_batch_unrelated_write_does_not_join_visible_request(wyb, root_element):
    async def main():
        query, write, data, gates = loader()
        typed, type_text = create_signal("a")
        wyb["reconciler"].render(div(span(query), span(typed), p(data)), root_element)
        await tick()
        write(1)
        type_text("b")
        await tick()
        assert texts(root_element) == ["0", "b", "0"]
        gates[1].set()
        await tick()
        assert texts(root_element) == ["1", "b", "1"]

    asyncio.run(main())


@pytest.mark.parametrize("cached", [False, True])
def test_resolve_expression_waits_for_quiet_refresh(wyb, cached):
    async def main():
        gate = asyncio.Event()
        calls = 0

        async def load():
            nonlocal calls
            calls += 1
            if calls > 1:
                await gate.wait()
            return calls

        data = create_root(lambda dispose: create_memo(load))
        expression = create_root(lambda dispose: create_memo(lambda: data() * 10)) if cached else lambda: data() * 10
        assert expression() == 10
        refresh(data)
        waiting = asyncio.ensure_future(resolve(expression))
        await tick()
        assert not waiting.done()
        gate.set()
        assert await waiting == 20

    asyncio.run(main())


def test_until_returns_settled_authoritative_value(wyb):
    async def main():
        gate = asyncio.Event()
        count = 0

        async def load():
            nonlocal count
            count += 1
            if count > 1:
                await gate.wait()
            return {"count": count}

        data = create_root(lambda dispose: create_memo(load))
        refresh(data)
        waiting = asyncio.ensure_future(until(data))
        await tick()
        assert not waiting.done()
        gate.set()
        assert await waiting == {"count": 2}

    asyncio.run(main())


@pytest.mark.parametrize("shared", [False, True])
def test_actions_join_only_when_they_share_writes(wyb, root_element, shared):
    async def main():
        left, sl = create_signal(0)
        right, sr = (left, sl) if shared else create_signal(0)
        lg, rg = asyncio.Event(), asyncio.Event()

        @action
        async def edit(setter, gate, value):
            setter(value)
            await gate.wait()

        wyb["reconciler"].render(div(span(left), span(right)), root_element)
        a, b = edit(sl, lg, 1), edit(sr, rg, 2)
        await tick()
        rg.set()
        await b
        await tick()
        assert texts(root_element) == (["0", "0"] if shared else ["0", "2"])
        lg.set()
        await a
        await tick()
        assert texts(root_element) == (["2", "2"] if shared else ["1", "2"])

    asyncio.run(main())


def test_optimistic_operations_are_removed_per_action(wyb):
    async def main():
        base, _ = create_signal(0)
        shown, edit = create_optimistic(base)
        first, second = asyncio.Event(), asyncio.Event()

        @action
        async def add(amount, gate):
            edit(lambda value: value + amount)
            await gate.wait()

        a, b = add(1, first), add(10, second)
        await tick()
        assert shown() == 11
        second.set()
        await b
        await tick()
        assert shown() == 1
        first.set()
        await a
        await tick()
        assert shown() == 0

    asyncio.run(main())


def test_optimistic_store_edits_rebase_independently(wyb):
    async def main():
        base, write_base = create_store({"count": 0})
        shown, edit = create_optimistic_store(lambda: deep(base), {})
        first, second = asyncio.Event(), asyncio.Event()

        @action
        async def add(amount, gate):
            edit(lambda draft: draft.update(count=draft["count"] + amount))
            await gate.wait()

        a, b = add(1, first), add(10, second)
        await tick()
        assert shown.count == 11
        write_base(lambda draft: draft.update(count=100))
        await tick()
        assert shown.count == 111
        second.set()
        await b
        await tick()
        assert shown.count == 101
        first.set()
        await a
        await tick()
        assert shown.count == 100

    asyncio.run(main())


def test_affects_store_subtree_is_precise(wyb):
    async def main():
        store, _ = create_store({"left": {"name": "a"}, "right": {"name": "b"}})
        gate = asyncio.Event()

        @action
        async def edit():
            affects(store.left)
            await gate.wait()

        future = edit()
        await tick()
        assert is_pending(lambda: store.left.name)
        assert not is_pending(lambda: store.right.name)
        gate.set()
        await future
        await tick()
        assert not is_pending(lambda: store.left.name)

    asyncio.run(main())


def test_superseded_request_cannot_publish_stale_result(wyb, root_element):
    async def main():
        query, write, data, gates = loader()
        wyb["reconciler"].render(div(span(query), p(data)), root_element)
        await tick()
        write(1)
        await tick()
        write(2)
        await tick()
        gates[1].set()
        await tick()
        assert texts(root_element) == ["0", "0"]
        gates[2].set()
        await tick()
        assert texts(root_element) == ["2", "2"]
        assert not _core._transitions

    asyncio.run(main())


def test_compute_resources_survive_until_publication_and_abandoned_resources_dispose(wyb, root_element):
    from wybthon import create_memo, on_cleanup

    async def main():
        query, write, data, gates = loader()
        cleaned = []
        owners = {}

        def content():
            value = query()
            owners[value] = create_memo(lambda: value)
            on_cleanup(lambda: cleaned.append(value))
            return span(owners[value])

        root = wyb["reconciler"].render(div(content, p(data)), root_element)
        await tick()
        write(1)
        await tick()
        assert not owners[0]._disposed
        assert cleaned == []
        write(2)
        await tick()
        assert owners[1]._disposed
        assert not owners[0]._disposed
        assert cleaned == [1]
        gates[2].set()
        await tick()
        assert owners[0]._disposed
        assert not owners[2]._disposed
        assert cleaned == [1, 0]
        root.dispose()
        assert owners[2]._disposed
        assert cleaned == [1, 0, 2]

    asyncio.run(main())


def test_removing_async_consumer_releases_held_input(wyb, root_element):
    async def main():
        query, write, data, gates = loader()
        show, set_show = create_signal(True)
        wyb["reconciler"].render(div(span(query), lambda: p(data) if show() else None), root_element)
        await tick()
        write(1)
        await tick()
        assert texts(root_element) == ["0", "0"]
        set_show(False)
        await tick()
        assert texts(root_element) == ["1"]
        assert not _core._transitions
        gates[1].set()
        await tick()

    asyncio.run(main())


def test_async_projection_holds_with_its_visible_fields(wyb, root_element):
    from wybthon import create_projection

    async def main():
        query, write = create_signal(0)
        gate = asyncio.Event()

        async def load():
            value = query()
            if value:
                await gate.wait()
            return {"name": str(value)}

        projection = create_projection(load, {})
        wyb["reconciler"].render(div(span(query), p(lambda: projection.name)), root_element)
        await tick()
        write(1)
        await tick()
        assert texts(root_element) == ["0", "0"]
        gate.set()
        await tick()
        assert texts(root_element) == ["1", "1"]

    asyncio.run(main())


@pytest.mark.parametrize("store_target", [False, True])
def test_affects_updates_an_already_mounted_indicator(wyb, root_element, store_target):
    async def main():
        target, _ = create_store({"child": {"name": "a"}}) if store_target else create_signal("a")
        read = (lambda: target.child.name) if store_target else target
        affected = target.child if store_target else target
        gate = asyncio.Event()

        @action
        async def edit():
            affects(affected)
            await gate.wait()

        wyb["reconciler"].render(span(lambda: str(is_pending(read))), root_element)
        await tick()
        assert texts(root_element) == ["False"]
        future = edit()
        await tick()
        assert texts(root_element) == ["True"]
        gate.set()
        await future
        await tick()
        assert texts(root_element) == ["False"]

    asyncio.run(main())


def test_new_consumer_during_hold_reads_published_version(wyb, root_element):
    async def main():
        query, write, data, gates = loader()
        show, set_show = create_signal(False)
        wyb["reconciler"].render(div(span(query), p(data), lambda: span(query) if show() else None), root_element)
        await tick()
        write(1)
        await tick()
        set_show(True)
        await tick()
        assert texts(root_element) == ["0", "0", "0"]
        gates[1].set()
        await tick()
        assert texts(root_element) == ["1", "1", "1"]

    asyncio.run(main())


def test_diagnostics_identify_independent_blockers_without_joining_them(wyb, root_element):
    from wybthon.diagnostics import inspect_graph, inspect_transitions, runtime_stats

    async def main():
        left, write_left, dl, gl = loader()
        right, write_right, dr, gr = loader()
        root = wyb["reconciler"].render(div(span(left), p(dl), span(right), p(dr)), root_element)
        await tick()
        write_left(1)
        write_right(1)
        await tick()
        before = inspect_transitions()
        assert len(before) == 2
        assert {id(dl), id(dr)} == {item for tx in before for item in tx["pending"]}
        assert all(tx["held"] and tx["applies"] for tx in before)
        report = inspect_graph(root._owner)
        assert report["transitions"] == before
        assert runtime_stats()["transitions"] == 2
        gl[1].set()
        gr[1].set()
        await tick()
        assert runtime_stats()["held_nodes"] == 0

    asyncio.run(main())


def test_resolve_stream_waits_for_first_fresh_yield_not_stream_completion(wyb):
    async def main():
        gates = [asyncio.Event(), asyncio.Event()]
        generation = 0
        closed = []

        async def stream():
            nonlocal generation
            run = generation
            generation += 1
            try:
                await gates[run].wait()
                yield run + 1
                await asyncio.Event().wait()
            finally:
                closed.append(run)

        data = create_root(lambda dispose: create_memo(stream))
        first = asyncio.ensure_future(resolve(lambda: data() * 10))
        await tick()
        assert not first.done()
        gates[0].set()
        await tick()
        assert first.done()
        assert await first == 10
        fresh = asyncio.ensure_future(refresh(data))
        await tick()
        assert not fresh.done()
        assert closed == [0]
        gates[1].set()
        await tick()
        assert fresh.done()
        assert await fresh == 2
        data.dispose()
        await tick()
        assert closed == [0, 1]

    asyncio.run(main())


@pytest.mark.parametrize("cancel_first", [True, False])
def test_canceling_one_action_preserves_other_optimistic_edits(wyb, cancel_first):
    async def main():
        shown, edit = create_optimistic_store({"n": 0})
        gates = [asyncio.Event(), asyncio.Event()]

        @action
        async def change(value, gate):
            edit(lambda draft: draft.update(n=draft.n + value))
            await gate.wait()

        first, second = change(1, gates[0]), change(10, gates[1])
        await tick()
        canceled, retained = (first, second) if cancel_first else (second, first)
        canceled.cancel()
        with pytest.raises(asyncio.CancelledError):
            await canceled
        await tick()
        assert shown.n == (10 if cancel_first else 1)
        gates[1 if cancel_first else 0].set()
        await retained
        await tick()
        assert shown.n == 0
        assert not _core._transitions

    asyncio.run(main())


def test_speculative_error_does_not_replace_visible_boundary(wyb, root_element):
    from wybthon import Errored

    async def main():
        query, write, data, gates = loader()

        def value():
            if query() == 1:
                raise ValueError("temporary")
            return str(query())

        wyb["reconciler"].render(
            div(Errored(lambda: span(value), fallback=lambda error: p("error")), p(data)), root_element
        )
        await tick()
        write(1)
        await tick()
        assert texts(root_element) == ["0", "0"]
        write(2)
        await tick()
        gates[2].set()
        await tick()
        assert texts(root_element) == ["2", "2"]

    asyncio.run(main())


@pytest.mark.parametrize("store_form", [False, True])
def test_acknowledgement_never_publishes_authoritative_value_plus_its_own_overlay(wyb, store_form):
    from wybthon import create_effect

    async def main():
        gate = asyncio.Event()
        if store_form:
            base, write = create_store({"n": 0})
            shown, edit = create_optimistic_store(lambda: deep(base), {})

            def read():
                return shown.n

            def optimistic():
                edit(lambda draft: draft.update(n=draft.n + 1))

            def acknowledge():
                write(lambda draft: draft.update(n=1))

        else:
            base, write = create_signal(0)
            shown, edit = create_optimistic(base)
            read = shown

            def optimistic():
                edit(lambda value: value + 1)

            def acknowledge():
                write(1)

        observed = []
        create_root(lambda dispose: create_effect(read, observed.append))

        @action
        async def save():
            optimistic()
            await gate.wait()
            acknowledge()

        future = save()
        await tick()
        assert observed[-1] == 1
        gate.set()
        await future
        await tick()
        assert 2 not in observed
        assert read() == 1

    asyncio.run(main())


def test_optimistic_noop_still_updates_pending_indicator(wyb, root_element):
    async def main():
        shown, edit = create_optimistic_store({"n": 0})
        gate = asyncio.Event()

        @action
        async def save():
            edit(lambda draft: draft.update(n=0))
            await gate.wait()

        wyb["reconciler"].render(span(lambda: str(is_pending(lambda: shown.n))), root_element)
        await tick()
        future = save()
        await tick()
        assert texts(root_element) == ["True"]
        gate.set()
        await future
        await tick()
        assert texts(root_element) == ["False"]

    asyncio.run(main())


def test_lifecycle_callbacks_and_nested_effects_wait_for_preparation_publication(wyb, root_element):
    from wybthon import create_effect, on_settled

    async def main():
        query, write, data, gates = loader()
        settled, effects = [], []

        def content():
            value = query()
            on_settled(lambda: settled.append(value))
            create_effect(lambda: value, effects.append)
            return span(str(value))

        root = wyb["reconciler"].render(div(content, p(data)), root_element)
        await tick()
        assert settled == effects == [0]
        write(1)
        await tick()
        assert settled == effects == [0]
        write(2)
        await tick()
        assert settled == effects == [0]
        gates[2].set()
        await tick()
        assert settled == effects == [0, 2]
        root.dispose()

    asyncio.run(main())


def test_unmount_releases_publication_without_an_explicit_flush(wyb, root_element):
    async def main():
        query, write, data, gates = loader()
        root = wyb["reconciler"].render(div(span(query), p(data)), root_element)
        await tick()
        write(1)
        await tick()
        assert _core._transitions
        root.dispose()
        for _ in range(3):
            await asyncio.sleep(0)
        assert not _core._transitions
        assert query() == 1
        gates[1].set()
        await tick()

    asyncio.run(main())


def test_until_store_truthiness_uses_authoritative_view(wyb):
    async def main():
        base, write = create_store([])
        shown, edit = create_optimistic_store(lambda: deep(base), [])
        edit(lambda draft: draft.append("optimistic"))
        waiting = asyncio.ensure_future(until(lambda: shown))
        await tick()
        assert len(shown) == 1
        assert not waiting.done()
        write(lambda draft: draft.append("confirmed"))
        await tick()
        assert waiting.done()
        assert await waiting is shown

    asyncio.run(main())


def test_unchanged_refresh_does_not_reuse_a_completed_action_group(wyb):
    async def main():
        server = [0]

        async def load():
            return server[0]

        data = create_root(lambda dispose: create_memo(load))

        @action
        async def save():
            await refresh(data)

        await save()
        await tick()
        assert not _core._transitions
        server[0] = 1
        await refresh(data)
        await tick()
        assert data() == 1
        assert not _core._held

    asyncio.run(main())


def test_projection_refresh_lands_with_its_action(wyb, root_element):
    from wybthon import create_projection

    async def main():
        server = [0]
        gate = asyncio.Event()

        async def load():
            return {"n": server[0]}

        view = create_projection(load, {})
        wyb["reconciler"].render(span(lambda: str(view.n)), root_element)
        await tick()

        @action
        async def save():
            server[0] = 1
            await refresh(view)
            await gate.wait()

        future = save()
        await tick()
        assert texts(root_element) == ["0"]
        assert latest(lambda: view.n) == 1
        gate.set()
        await future
        await tick()
        assert texts(root_element) == ["1"]

    asyncio.run(main())
