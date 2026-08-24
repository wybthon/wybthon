"""Tests for the SolidJS 2.0-parity reactivity primitives.

Covers functional signal setters, `create_render_effect` phase
ordering, `catch_error`, `create_unique_id`, `create_reaction`,
`on_error`, split effects, async memos (`NotReadyError`, `is_pending`,
`latest`), `action`, and `create_optimistic`.
"""

import asyncio

import pytest

from wybthon.reactivity import (
    NotReadyError,
    action,
    catch_error,
    create_effect,
    create_memo,
    create_optimistic,
    create_reaction,
    create_render_effect,
    create_root,
    create_signal,
    create_unique_id,
    flush,
    is_pending,
    latest,
    on_error,
)

# ---------------------------------------------------------------------------
# Functional setters
# ---------------------------------------------------------------------------


def test_setter_functional_update():
    count, set_count = create_signal(1)
    result = set_count(lambda c: c + 9)
    assert count() == 10
    assert result == 10


def test_setter_plain_value():
    count, set_count = create_signal(0)
    set_count(42)
    assert count() == 42


def test_setter_storing_callable_requires_wrapping():
    def stored():
        return "hello"

    fn, set_fn = create_signal(None)
    set_fn(lambda _prev: stored)
    assert fn() is stored


# ---------------------------------------------------------------------------
# Render effects and phase ordering
# ---------------------------------------------------------------------------


def test_render_effects_run_before_user_effects():
    order = []
    count, set_count = create_signal(0)

    create_effect(lambda: (count(), order.append("effect"))[1])
    create_render_effect(lambda: (count(), order.append("render"))[1])

    order.clear()
    set_count(1)
    flush()
    assert order == ["render", "effect"]


def test_memo_derives_before_effects():
    """A memo read by an effect is already up to date when the effect runs."""
    count, set_count = create_signal(1)
    double = create_memo(lambda: count() * 2)
    seen = []

    create_effect(lambda: seen.append((count(), double())))

    assert seen[-1] == (1, 2)
    set_count(5)
    flush()
    # The user effect must observe the already-updated derived value.
    assert (5, 10) in seen


# ---------------------------------------------------------------------------
# Split effects (SolidJS 2.0's createEffect(compute, apply))
# ---------------------------------------------------------------------------


def test_split_effect_apply_receives_computed_value():
    count, set_count = create_signal(1)
    applied = []

    create_effect(lambda: count() * 10, lambda v: applied.append(v))
    assert applied == [10]

    set_count(3)
    flush()
    assert applied == [10, 30]


def test_split_effect_apply_is_untracked():
    """Signals read in the apply phase must not become dependencies."""
    count, set_count = create_signal(0)
    other, set_other = create_signal(100)
    runs = []

    create_effect(lambda: count(), lambda v: runs.append((v, other())))
    assert runs == [(0, 100)]

    set_other(200)
    flush()
    assert runs == [(0, 100)], "apply-phase read must not subscribe"

    set_count(1)
    flush()
    assert runs[-1] == (1, 200)


# ---------------------------------------------------------------------------
# catch_error
# ---------------------------------------------------------------------------


def test_catch_error_synchronous():
    caught = []

    def boom():
        raise ValueError("sync fail")

    result = catch_error(boom, lambda e: caught.append(e))
    assert result is None
    assert isinstance(caught[0], ValueError)


def test_catch_error_returns_value_on_success():
    assert catch_error(lambda: 42, lambda e: None) == 42


def test_catch_error_catches_later_effect_errors():
    caught = []
    count, set_count = create_signal(0)

    def setup():
        def effect_body():
            if count() > 0:
                raise RuntimeError("effect fail")

        create_effect(effect_body)
        return "ok"

    result = catch_error(setup, lambda e: caught.append(e))
    assert result == "ok"
    assert caught == []

    set_count(1)
    flush()
    assert len(caught) == 1
    assert isinstance(caught[0], RuntimeError)


def test_effect_error_without_handler_propagates():
    count, set_count = create_signal(0)

    def root_body(dispose):
        def effect_body():
            if count() > 0:
                raise RuntimeError("unhandled")

        create_effect(effect_body)

    create_root(root_body)
    set_count(1)
    with pytest.raises(RuntimeError):
        flush()


# ---------------------------------------------------------------------------
# create_unique_id
# ---------------------------------------------------------------------------


def test_create_unique_id_unique_and_stringy():
    ids = {create_unique_id() for _ in range(100)}
    assert len(ids) == 100
    assert all(isinstance(i, str) and i for i in ids)


# ---------------------------------------------------------------------------
# Async memos: NotReadyError, stale-while-revalidate, is_pending, latest
# ---------------------------------------------------------------------------


def test_async_memo_not_ready_then_resolves():
    async def run():
        release = asyncio.Event()

        async def load():
            await release.wait()
            return 42

        value = create_memo(load)

        with pytest.raises(NotReadyError):
            value()
        assert is_pending(value) is True
        assert latest(value) is None

        release.set()
        await asyncio.sleep(0.01)

        assert value() == 42
        assert is_pending(value) is False
        assert latest(value) == 42

    asyncio.run(run())


def test_async_memo_stale_while_revalidate():
    async def run():
        source, set_source = create_signal(1)
        gate = asyncio.Event()
        gate.set()

        async def load():
            n = source()
            await gate.wait()
            return n * 10

        value = create_memo(load)
        await asyncio.sleep(0.01)
        assert value() == 10

        # Trigger a revalidation that blocks: reads serve the stale value.
        gate.clear()
        set_source(2)
        await asyncio.sleep(0.01)
        assert value() == 10, "stale value served while revalidating"
        assert is_pending(value) is True

        gate.set()
        await asyncio.sleep(0.01)
        assert value() == 20
        assert is_pending(value) is False

    asyncio.run(run())


def test_async_memo_error_raises_on_read():
    async def run():
        async def load():
            raise ValueError("load failed")

        value = create_memo(load)
        await asyncio.sleep(0.01)
        with pytest.raises(ValueError):
            value()

    asyncio.run(run())


def test_sync_memo_reading_pending_async_becomes_pending():
    """NotReady propagates through derived sync memos."""

    async def run():
        release = asyncio.Event()

        async def load():
            await release.wait()
            return 5

        base = create_memo(load)
        derived = create_memo(lambda: base() + 1)

        with pytest.raises(NotReadyError):
            derived()
        assert is_pending(derived) is True

        release.set()
        await asyncio.sleep(0.01)
        assert derived() == 6

    asyncio.run(run())


def test_effect_suspends_until_async_source_ready():
    async def run():
        release = asyncio.Event()

        async def load():
            await release.wait()
            return "data"

        value = create_memo(load)
        seen = []
        create_effect(lambda: seen.append(value()))
        assert seen == [], "effect must not observe a not-ready value"

        release.set()
        await asyncio.sleep(0.01)
        assert seen == ["data"]

    asyncio.run(run())


def test_async_effect_body():
    async def run():
        count, set_count = create_signal(1)
        seen = []

        async def body():
            n = count()
            await asyncio.sleep(0)
            seen.append(n)

        create_effect(body)
        await asyncio.sleep(0.01)
        assert seen == [1]

        set_count(2)
        await asyncio.sleep(0.01)
        assert seen == [1, 2]

    asyncio.run(run())


# ---------------------------------------------------------------------------
# action / create_optimistic
# ---------------------------------------------------------------------------


def test_action_pending_tracks_inflight_run():
    async def run():
        release = asyncio.Event()
        done = []

        @action
        async def save(value):
            await release.wait()
            done.append(value)
            return value

        assert save.pending() is False
        task = asyncio.ensure_future(save(7))
        await asyncio.sleep(0)
        assert save.pending() is True

        release.set()
        result = await task
        assert result == 7
        assert done == [7]
        assert save.pending() is False

    asyncio.run(run())


def test_action_error_still_clears_pending():
    async def run():
        @action
        async def fail():
            raise ValueError("nope")

        with pytest.raises(ValueError):
            await fail()
        assert fail.pending() is False

    asyncio.run(run())


def test_create_optimistic_reverts_when_action_settles():
    async def run():
        todos, set_todos = create_signal(["a"])
        optimistic, set_optimistic = create_optimistic(todos)
        release = asyncio.Event()

        @action
        async def add_todo(title):
            set_optimistic(lambda cur: cur + [title])
            await release.wait()
            # Server confirmed: apply to the real source.
            set_todos(todos() + [title])

        task = asyncio.ensure_future(add_todo("b"))
        await asyncio.sleep(0)
        assert optimistic() == ["a", "b"], "optimistic value visible while in flight"
        assert todos() == ["a"]

        release.set()
        await task
        await asyncio.sleep(0)
        # Action settled: optimistic reverts to (now-updated) source.
        assert optimistic() == ["a", "b"]
        assert todos() == ["a", "b"]

    asyncio.run(run())


def test_create_optimistic_reverts_on_failure():
    async def run():
        count, _set_count = create_signal(0)
        optimistic, set_optimistic = create_optimistic(count)

        @action
        async def bump():
            set_optimistic(1)
            raise ValueError("server rejected")

        with pytest.raises(ValueError):
            await bump()
        await asyncio.sleep(0)
        assert optimistic() == 0, "failed action reverts the optimistic value"

    asyncio.run(run())


# ---------------------------------------------------------------------------
# create_reaction
# ---------------------------------------------------------------------------


def test_create_reaction_fires_once_per_track():
    count, set_count = create_signal(0)
    fired = []
    track = create_reaction(lambda: fired.append(count.peek()))

    track(count)
    assert fired == []

    set_count(1)
    flush()
    assert len(fired) == 1

    # Tracking stopped: further changes don't fire.
    set_count(2)
    flush()
    assert len(fired) == 1

    # Re-arm.
    track(count)
    set_count(3)
    flush()
    assert len(fired) == 2


def test_create_reaction_tracks_multiple_sources():
    a, set_a = create_signal(0)
    b, set_b = create_signal(0)
    fired = []
    track = create_reaction(lambda: fired.append("changed"))

    track(lambda: (a(), b()))
    set_b(1)
    flush()
    assert fired == ["changed"]
    set_a(1)
    flush()
    assert fired == ["changed"]


# ---------------------------------------------------------------------------
# on_error
# ---------------------------------------------------------------------------


def test_on_error_catches_child_effect_error():
    count, set_count = create_signal(0)
    errors = []

    def root_body(dispose):
        on_error(lambda exc: errors.append(str(exc)))

        def effect_body():
            if count() > 0:
                raise RuntimeError("boom")

        create_effect(effect_body)

    create_root(root_body)
    assert errors == []
    set_count(1)
    flush()
    assert errors == ["boom"]


def test_on_error_chains_multiple_handlers():
    count, set_count = create_signal(0)
    order = []

    def root_body(dispose):
        on_error(lambda exc: order.append("first"))
        on_error(lambda exc: order.append("second"))

        def effect_body():
            if count() > 0:
                raise RuntimeError("boom")

        create_effect(effect_body)

    create_root(root_body)
    set_count(1)
    flush()
    assert order == ["first", "second"]


def test_on_error_outside_scope_raises():
    try:
        on_error(lambda exc: None)
        raised = False
    except RuntimeError:
        raised = True
    assert raised


# ---------------------------------------------------------------------------
# create_memo equals=
# ---------------------------------------------------------------------------


def test_memo_custom_equals_suppresses_notification():
    items, set_items = create_signal([1, 2, 3])
    # Only notify observers when the length changes.
    head = create_memo(lambda: list(items()), equals=lambda a, b: len(a) == len(b))
    runs = []
    create_effect(lambda: runs.append(head()))
    assert len(runs) == 1

    set_items([4, 5, 6])  # same length: memo recomputes, observers stay quiet
    flush()
    assert len(runs) == 1

    set_items([1, 2])  # length changed: observers re-run
    flush()
    assert len(runs) == 2


def test_memo_equals_false_always_notifies():
    count, set_count = create_signal(0)
    parity = create_memo(lambda: count() % 2, equals=False)
    runs = []
    create_effect(lambda: runs.append(parity()))
    assert len(runs) == 1

    set_count(2)  # parity unchanged (0), but equals=False forces a re-run
    flush()
    assert len(runs) == 2


# ---------------------------------------------------------------------------
# Public peek on getters
# ---------------------------------------------------------------------------


def test_signal_getter_peek_does_not_track():
    count, set_count = create_signal(0)
    runs = []
    create_effect(lambda: runs.append(count.peek()))
    assert runs == [0]
    set_count(5)
    flush()
    # peek didn't subscribe, so the effect never re-runs.
    assert runs == [0]
    assert count.peek() == 5


def test_memo_getter_peek_recomputes_without_tracking():
    count, set_count = create_signal(1)
    doubled = create_memo(lambda: count() * 2)
    assert doubled.peek() == 2

    runs = []
    create_effect(lambda: runs.append(doubled.peek()))
    assert runs == [2]

    set_count(10)
    flush()
    # The memo recomputes lazily on peek, but the effect wasn't subscribed.
    assert doubled.peek() == 20
    assert runs == [2]
