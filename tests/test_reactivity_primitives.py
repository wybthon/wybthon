"""Tests for the SolidJS-parity reactivity primitives.

Covers functional signal setters, `create_render_effect` /
`create_computed` phase ordering, `catch_error`, `create_unique_id`,
`create_deferred`, and the Solid-shaped `Resource` accessor.
"""

import asyncio

from wybthon.reactivity import (
    catch_error,
    create_computed,
    create_deferred,
    create_effect,
    create_memo,
    create_render_effect,
    create_resource,
    create_root,
    create_signal,
    create_unique_id,
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
# Render effects and computed
# ---------------------------------------------------------------------------


def test_render_effects_run_before_user_effects():
    order = []
    count, set_count = create_signal(0)

    create_effect(lambda: (count(), order.append("effect"))[1])
    create_render_effect(lambda: (count(), order.append("render"))[1])

    order.clear()
    set_count(1)
    assert order == ["render", "effect"]


def test_create_computed_derives_before_effects():
    count, set_count = create_signal(1)
    double, set_double = create_signal(2)
    seen = []

    create_computed(lambda: set_double(count() * 2))
    create_effect(lambda: seen.append((count(), double())))

    assert seen[-1] == (1, 2)
    set_count(5)
    # The user effect must observe the already-updated derived signal.
    assert (5, 10) in seen


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
    try:
        set_count(1)
        raised = False
    except RuntimeError:
        raised = True
    assert raised


# ---------------------------------------------------------------------------
# create_unique_id
# ---------------------------------------------------------------------------


def test_create_unique_id_unique_and_stringy():
    ids = {create_unique_id() for _ in range(100)}
    assert len(ids) == 100
    assert all(isinstance(i, str) and i for i in ids)


# ---------------------------------------------------------------------------
# create_deferred
# ---------------------------------------------------------------------------


def test_create_deferred_trails_source():
    async def run():
        count, set_count = create_signal(0)
        deferred = create_deferred(count)
        assert deferred() == 0

        set_count(5)
        # Source updated, deferred waits for the next loop tick.
        assert count() == 5
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert deferred() == 5

    asyncio.run(run())


def test_create_deferred_without_loop_updates_immediately():
    count, set_count = create_signal(0)
    deferred = create_deferred(count)
    set_count(3)
    assert deferred() == 3


# ---------------------------------------------------------------------------
# Resource accessor shape
# ---------------------------------------------------------------------------


def test_resource_is_callable_accessor():
    async def run():
        async def fetcher():
            return {"name": "Ada"}

        res = create_resource(fetcher)
        assert res.loading is True
        assert res.state == "pending"
        await asyncio.sleep(0.01)
        assert res.loading is False
        assert res.state == "ready"
        assert res() == {"name": "Ada"}
        assert res.latest == {"name": "Ada"}
        assert res.error is None

    asyncio.run(run())


def test_resource_error_state():
    async def run():
        async def fetcher():
            raise ValueError("fetch failed")

        res = create_resource(fetcher)
        await asyncio.sleep(0.01)
        assert res.state == "errored"
        assert isinstance(res.error, ValueError)
        assert res.loading is False

    asyncio.run(run())


def test_resource_mutate():
    async def run():
        async def fetcher():
            return 1

        res = create_resource(fetcher)
        await asyncio.sleep(0.01)
        assert res() == 1
        res.mutate(99)
        assert res() == 99
        res.mutate(lambda v: v + 1)
        assert res() == 100
        assert res.state == "ready"

    asyncio.run(run())


def test_resource_refetch_enters_refreshing_state():
    async def run():
        counter = [0]

        async def fetcher():
            counter[0] += 1
            return counter[0]

        res = create_resource(fetcher)
        await asyncio.sleep(0.01)
        assert res() == 1

        res.refetch()
        # Previous data stays readable while refreshing.
        assert res.state == "refreshing"
        assert res.latest == 1
        await asyncio.sleep(0.01)
        assert res() == 2

    asyncio.run(run())


def test_resource_source_passes_value_and_skips_none():
    async def run():
        user_id, set_user_id = create_signal(None)
        fetched = []

        async def fetcher(uid):
            fetched.append(uid)
            return f"user-{uid}"

        res = create_resource(user_id, fetcher)
        await asyncio.sleep(0.01)
        assert fetched == []
        assert res.state == "unresolved"

        set_user_id(7)
        await asyncio.sleep(0.01)
        assert fetched == [7]
        assert res() == "user-7"

        set_user_id(8)
        await asyncio.sleep(0.01)
        assert fetched == [7, 8]
        assert res() == "user-8"

    asyncio.run(run())


def test_resource_tracked_in_effect():
    async def run():
        async def fetcher():
            return "done"

        res = create_resource(fetcher)
        seen = []
        create_effect(lambda: seen.append(res.loading))
        assert seen[-1] is True
        await asyncio.sleep(0.01)
        assert seen[-1] is False

    asyncio.run(run())


def test_memo_of_resource_data():
    async def run():
        async def fetcher():
            return [1, 2, 3]

        res = create_resource(fetcher)
        total = create_memo(lambda: sum(res() or []))
        assert total() == 0
        await asyncio.sleep(0.01)
        assert total() == 6

    asyncio.run(run())
