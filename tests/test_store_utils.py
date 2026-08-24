"""Tests for store utilities: reconcile, unwrap, create_projection, create_optimistic_store."""

import asyncio

from wybthon.reactivity import action, create_effect, create_signal, flush
from wybthon.store import (
    create_optimistic_store,
    create_projection,
    create_store,
    reconcile,
    unwrap,
)

# ---------------------------------------------------------------------------
# unwrap
# ---------------------------------------------------------------------------


def test_unwrap_returns_raw_dict():
    initial = {"count": 0, "user": {"name": "Ada"}}
    store, _ = create_store(initial)
    assert unwrap(store) is initial


def test_unwrap_nested_proxy():
    store, _ = create_store({"user": {"name": "Ada"}})
    raw = unwrap(store.user)
    assert raw == {"name": "Ada"}
    assert isinstance(raw, dict)


def test_unwrap_passthrough_for_plain_values():
    assert unwrap(42) == 42
    assert unwrap("x") == "x"


# ---------------------------------------------------------------------------
# reconcile
# ---------------------------------------------------------------------------


def test_reconcile_updates_changed_leaves_only():
    store, set_store = create_store({"a": 1, "b": 2})
    a_seen = []
    b_seen = []
    create_effect(lambda: a_seen.append(store.a))
    create_effect(lambda: b_seen.append(store.b))

    set_store(reconcile({"a": 1, "b": 3}))
    flush()
    assert a_seen == [1], "unchanged leaf must not re-notify"
    assert b_seen == [2, 3]


def test_reconcile_preserves_item_identity_by_key():
    todos = [{"id": 1, "text": "one"}, {"id": 2, "text": "two"}]
    store, set_store = create_store({"todos": todos})
    original_first = unwrap(store)["todos"][0]

    incoming = {
        "todos": [
            {"id": 1, "text": "one"},
            {"id": 2, "text": "TWO!"},
            {"id": 3, "text": "three"},
        ]
    }
    set_store(reconcile(incoming))

    raw = unwrap(store)["todos"]
    assert raw[0] is original_first, "key-matched item keeps identity"
    assert raw[1]["text"] == "TWO!"
    assert [t["id"] for t in raw] == [1, 2, 3]


def test_reconcile_removes_missing_keys():
    store, set_store = create_store({"a": 1, "b": 2})
    set_store(reconcile({"a": 1}))
    assert "b" not in unwrap(store)
    assert store.b is None


def test_reconcile_without_key_replaces_positionally():
    store, set_store = create_store({"items": [1, 2, 3]})
    set_store(reconcile({"items": [4, 5]}, key=None))
    assert unwrap(store)["items"] == [4, 5]


# ---------------------------------------------------------------------------
# create_projection
# ---------------------------------------------------------------------------


def test_projection_derives_from_signal():
    selected, set_selected = create_signal(1)

    flags = create_projection(
        lambda draft: draft.update({"selected_id": selected()}),
        {"selected_id": None},
    )
    assert flags.selected_id == 1

    set_selected(7)
    flush()
    assert flags.selected_id == 7


def test_projection_is_fine_grained():
    """Only leaves the projection actually changed should notify."""
    a, set_a = create_signal(1)
    b, set_b = create_signal(10)

    def project(draft):
        draft.a = a()
        draft.b = b()

    proj = create_projection(project, {"a": None, "b": None})

    a_seen = []
    b_seen = []
    create_effect(lambda: a_seen.append(proj.a))
    create_effect(lambda: b_seen.append(proj.b))
    assert (a_seen, b_seen) == ([1], [10])

    set_a(2)
    flush()
    assert a_seen == [1, 2]
    assert b_seen == [10], "untouched leaf must not re-notify"


def test_projection_is_read_only():
    proj = create_projection(lambda draft: draft.update({"x": 1}), {"x": 0})
    try:
        proj.x = 5
        raised = False
    except AttributeError:
        raised = True
    assert raised


# ---------------------------------------------------------------------------
# create_optimistic_store
# ---------------------------------------------------------------------------


def test_optimistic_store_reverts_when_action_settles():
    async def run():
        todos, set_todos = create_store({"items": [{"id": 1, "title": "a"}]})

        def base():
            len(todos.items)  # reactive read so the overlay re-bases on change
            return unwrap(todos)

        shown, set_shown = create_optimistic_store(base, {"items": [{"id": 1, "title": "a"}]})
        release = asyncio.Event()

        @action
        async def add(title):
            set_shown(lambda s: s.items.append({"id": 2, "title": title, "saving": True}))
            await release.wait()
            set_todos(lambda s: s.items.append({"id": 2, "title": title}))

        task = asyncio.ensure_future(add("b"))
        await asyncio.sleep(0)
        assert len(shown.items) == 2, "optimistic row visible while in flight"
        assert shown.items[1].title == "b"
        assert len(todos.items) == 1

        release.set()
        await task
        await asyncio.sleep(0)
        flush()
        # Action settled: overlay reverts to the (now-updated) base state.
        assert len(todos.items) == 2
        assert len(shown.items) == 2
        assert shown.items[1].title == "b"

    asyncio.run(run())


def test_optimistic_store_value_form_reverts_on_failure():
    async def run():
        shown, set_shown = create_optimistic_store({"items": [{"id": 1, "v": "a"}]})

        @action
        async def add():
            set_shown(lambda s: s.items.append({"id": 2, "v": "b"}))
            raise ValueError("server rejected")

        try:
            await add()
        except ValueError:
            pass
        await asyncio.sleep(0)
        flush()
        assert len(shown.items) == 1, "failed action reverts optimistic writes"
        assert shown.items[0].v == "a"

    asyncio.run(run())
