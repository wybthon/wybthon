"""Tests for store utilities: reconcile, unwrap, create_mutable."""

from wybthon.reactivity import create_effect
from wybthon.store import create_mutable, create_store, reconcile, unwrap

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
    assert a_seen == [1], "unchanged leaf must not re-notify"
    assert b_seen == [2, 3]


def test_reconcile_preserves_item_identity_by_key():
    todos = [{"id": 1, "text": "one"}, {"id": 2, "text": "two"}]
    store, set_store = create_store({"todos": todos})
    original_first = unwrap(store)["todos"][0]

    incoming = [{"id": 1, "text": "one"}, {"id": 2, "text": "TWO!"}, {"id": 3, "text": "three"}]
    set_store("todos", reconcile(incoming))

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
    set_store("items", reconcile([4, 5], key=None))
    assert unwrap(store)["items"] == [4, 5]


# ---------------------------------------------------------------------------
# create_mutable
# ---------------------------------------------------------------------------


def test_create_mutable_read_write():
    state = create_mutable({"count": 0})
    assert state.count == 0
    state.count = 5
    assert state.count == 5


def test_create_mutable_is_tracked():
    state = create_mutable({"count": 0})
    seen = []
    create_effect(lambda: seen.append(state.count))
    assert seen == [0]
    state.count = 1
    assert seen == [0, 1]


def test_create_mutable_item_assignment():
    state = create_mutable({"x": 1})
    state["x"] = 10
    assert state["x"] == 10
    assert state.x == 10


def test_create_mutable_unwrap():
    state = create_mutable({"a": 1})
    state.a = 2
    assert unwrap(state) == {"a": 2}


def test_create_mutable_rejects_non_dict():
    try:
        create_mutable([1, 2])
        raised = False
    except TypeError:
        raised = True
    assert raised
