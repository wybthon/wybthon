"""Tests for ``wybthon.store``: draft-first reactive stores.

Covers proxy reads, staged draft writes, fine-grained tracking, ``reconcile``,
``snapshot``/``deep``, derived stores and projections,
optimistic stores, and the dev-mode write-in-scope guard.
"""

import asyncio

import pytest

from wybthon import _warnings
from wybthon.reactivity import (
    WriteInScopeError,
    action,
    create_effect,
    create_memo,
    create_root,
    create_signal,
    create_tracked_effect,
    flush,
    untrack,
)
from wybthon.store import (
    create_optimistic_store,
    create_projection,
    create_store,
    deep,
    reconcile,
    snapshot,
)


def _counting_memo(fn):
    """Return ``(memo, runs)`` where ``runs`` grows by one per recompute."""
    runs = []

    def compute():
        runs.append(1)
        return fn()

    return create_memo(compute), runs


def _sample():
    return create_store(
        {
            "count": 0,
            "user": {"name": "Ada", "age": 36},
            "items": [{"id": 1, "text": "a", "done": False}, {"id": 2, "text": "b", "done": True}],
            "nums": [1, 2, 3],
        }
    )


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------


def test_attribute_and_bracket_reads(wyb):
    store, _ = _sample()
    assert store.count == 0
    assert store["count"] == 0
    assert store.user.name == "Ada"
    assert store["user"]["age"] == 36
    assert store["items"][0].text == "a"
    assert store["items"][1]["done"] is True
    assert store.nums[2] == 3


def test_missing_keys_and_indices_raise_python_errors(wyb):
    store, _ = _sample()
    with pytest.raises(AttributeError):
        _ = store.missing
    with pytest.raises(KeyError):
        _ = store["missing"]
    with pytest.raises(IndexError):
        _ = store.nums[10]


def test_negative_index_and_slice_reads(wyb):
    store, _ = _sample()
    assert store.nums[-1] == 3
    assert store.nums[0:2] == [1, 2]
    assert store["items"][-1].id == 2


def test_len_iteration_and_contains(wyb):
    store, _ = _sample()
    assert len(store) == 4
    assert set(store) == {"count", "user", "items", "nums"}
    assert "user" in store
    assert "nope" not in store
    assert len(store.nums) == 3
    assert list(store.nums) == [1, 2, 3]
    assert 2 in store.nums
    assert 9 not in store.nums
    assert [t.text for t in store["items"]] == ["a", "b"]


def test_bool_of_store(wyb):
    empty, _ = create_store({})
    full, _ = create_store({"a": 1})
    empty_list, _ = create_store([])
    assert not empty
    assert full
    assert not empty_list


def test_equality_against_plain_data(wyb):
    store, _ = _sample()
    assert store.user == {"name": "Ada", "age": 36}
    assert store.nums == [1, 2, 3]
    assert store.user != {"name": "Bob"}
    assert store.nums != [1]
    assert store.user == store["user"]
    assert not (store.user == 5)


def test_repr_does_not_raise(wyb):
    store, _ = _sample()
    assert "Ada" in repr(store)
    assert repr(store.nums) == "StoreList([1, 2, 3])"
    assert repr(store.user) == "Store({'name': 'Ada', 'age': 36})"


def test_nested_proxy_identity_is_stable(wyb):
    store, _ = _sample()
    assert store.user is store.user
    assert store["items"][0] is store["items"][0]
    assert store["items"] is store["items"]


def test_read_proxy_is_read_only(wyb):
    store, _ = _sample()
    with pytest.raises(AttributeError):
        store.count = 5
    with pytest.raises(TypeError):
        store["count"] = 5
    with pytest.raises(TypeError):
        store.nums[0] = 5


def test_mapping_methods_take_precedence_over_data_keys(wyb):
    store, set_store = create_store({"items": [1], "keys": "k", "values": "v", "get": "g"})
    assert store["items"] == [1]
    assert list(store.keys()) == ["items", "keys", "values", "get"]
    assert dict(store.items()) == {"items": [1], "keys": "k", "values": "v", "get": "g"}
    assert store.get("missing", 42) == 42
    set_store(lambda s: s.__setitem__("keys", "K"))
    flush()
    assert store["keys"] == "K"


def test_setter_rejects_unknown_modifier(wyb):
    _, set_store = _sample()
    with pytest.raises(TypeError):
        set_store(5)


def test_scalar_initial_requires_signal(wyb):
    with pytest.raises(TypeError):
        create_store(5)


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------


def test_write_is_staged_until_flush(wyb):
    store, set_store = _sample()
    assert store.count == 0
    set_store(lambda s: setattr(s, "count", 1))
    assert store.count == 0
    flush()
    assert store.count == 1


def test_write_nested_keys_and_list_items(wyb):
    store, set_store = _sample()

    def edit(s):
        s.user.name = "Grace"
        s["user"]["age"] = 40
        s["items"][0].done = True
        s.nums[1] = 20
        s.nums[-1] = 30

    set_store(edit)
    flush()
    assert store.user.name == "Grace"
    assert store.user.age == 40
    assert store["items"][0].done is True
    assert snapshot(store.nums) == [1, 20, 30]


def test_add_new_key_and_delete_key(wyb):
    store, set_store = _sample()
    assert store.get("extra") is None
    set_store(lambda s: setattr(s, "extra", "yes"))
    flush()
    assert store.extra == "yes"
    assert "extra" in store

    set_store(lambda s: s.__delitem__("extra"))
    flush()
    assert "extra" not in store
    assert store.get("extra") is None

    set_store(lambda s: delattr(s, "count"))
    flush()
    assert "count" not in store
    assert store.get("count") is None


def test_replace_nested_dict_wholesale(wyb):
    store, set_store = _sample()
    memo, runs = _counting_memo(lambda: store.user.name)
    assert memo() == "Ada"

    set_store(lambda s: setattr(s, "user", {"name": "Bob", "age": 1}))
    flush()
    assert memo() == "Bob"
    assert len(runs) == 2
    assert store.user.age == 1

    set_store(lambda s: setattr(s, "user", None))
    flush()
    assert store.user is None


def test_draft_reads_see_prior_writes_in_same_setter(wyb):
    store, set_store = _sample()
    seen = []

    def edit(s):
        s.count = 5
        seen.append(s.count)
        s.count = s.count + 1
        s.nums.append(4)
        seen.append(len(s.nums))
        seen.append(4 in s.nums)
        seen.append(list(s.nums))

    set_store(edit)
    assert seen == [5, 4, True, [1, 2, 3, 4]]
    flush()
    assert store.count == 6


def test_successive_setters_before_flush_compose(wyb):
    store, set_store = _sample()
    assert store.count == 0
    set_store(lambda s: setattr(s, "count", s.count + 1))
    set_store(lambda s: setattr(s, "count", s.count + 1))
    assert store.count == 0
    flush()
    assert store.count == 2


def test_list_append_extend_insert(wyb):
    store, set_store = _sample()

    def edit(s):
        s.nums.append(4)
        s.nums.extend([5, 6])
        s.nums.insert(0, 0)

    set_store(edit)
    flush()
    assert snapshot(store.nums) == [0, 1, 2, 3, 4, 5, 6]
    assert len(store.nums) == 7


def test_list_pop_remove_clear(wyb):
    store, set_store = _sample()
    popped = []
    set_store(lambda s: popped.append(s.nums.pop()))
    set_store(lambda s: popped.append(s.nums.pop(0)))
    flush()
    assert popped == [3, 1]
    assert snapshot(store.nums) == [2]

    set_store(lambda s: s.nums.remove(2))
    flush()
    assert snapshot(store.nums) == []

    set_store(lambda s: s["items"].clear())
    flush()
    assert len(store["items"]) == 0
    assert list(store["items"]) == []


def test_list_del_and_slice_assignment(wyb):
    store, set_store = _sample()
    set_store(lambda s: s.nums.__delitem__(0))
    flush()
    assert snapshot(store.nums) == [2, 3]

    set_store(lambda s: s.nums.__setitem__(slice(0, 1), [7, 8, 9]))
    flush()
    assert snapshot(store.nums) == [7, 8, 9, 3]


def test_list_sort_and_reverse(wyb):
    store, set_store = create_store({"nums": [3, 1, 2]})
    set_store(lambda s: s.nums.sort())
    flush()
    assert snapshot(store.nums) == [1, 2, 3]

    set_store(lambda s: s.nums.reverse())
    flush()
    assert snapshot(store.nums) == [3, 2, 1]

    set_store(lambda s: s.nums.sort(key=lambda n: -n, reverse=True))
    flush()
    assert snapshot(store.nums) == [1, 2, 3]


def test_list_of_dicts_append_then_read_new_item(wyb):
    store, set_store = _sample()
    set_store(lambda s: s["items"].append({"id": 3, "text": "c", "done": False}))
    flush()
    assert len(store["items"]) == 3
    assert store["items"][2].text == "c"
    assert store["items"][-1]["id"] == 3


def test_draft_update_merges_keys(wyb):
    store, set_store = _sample()
    set_store(lambda s: s.update({"count": 9, "flag": True}))
    flush()
    assert store.count == 9
    assert store.flag is True
    assert store.user.name == "Ada"


def test_setter_returning_dict_replaces_state(wyb):
    store, set_store = create_store({"a": 1, "b": 2})
    set_store(lambda s: {"a": 10, "b": 20})
    flush()
    assert snapshot(store) == {"a": 10, "b": 20}
    assert store.a == 10


def test_setter_returning_list_replaces_state(wyb):
    lst, set_lst = create_store([1, 2, 3])
    set_lst(lambda s: s.append(4))
    flush()
    assert snapshot(lst) == [1, 2, 3, 4]
    set_lst(lambda s: [9])
    flush()
    assert snapshot(lst) == [9]
    assert len(lst) == 1


def test_setter_accepts_plain_replacement_data(wyb):
    store, set_store = create_store({"a": 1})
    set_store({"a": 2})
    flush()
    assert store.a == 2


def test_writing_a_proxy_stores_plain_data(wyb):
    store, set_store = _sample()
    set_store(lambda s: s.__setitem__("first", s["items"][0]))
    flush()
    first = snapshot(store)["first"]
    assert isinstance(first, dict)
    assert first == {"id": 1, "text": "a", "done": False}
    assert store.first.text == "a"


# ---------------------------------------------------------------------------
# reconcile
# ---------------------------------------------------------------------------


def test_reconcile_keeps_identity_of_unchanged_items(wyb):
    store, set_store = _sample()
    memo, runs = _counting_memo(lambda: store["items"][0].text)
    assert memo() == "a"
    first = store["items"][0]

    set_store(
        reconcile(
            {
                "count": 0,
                "user": {"name": "Ada", "age": 36},
                "items": [{"id": 1, "text": "a", "done": False}, {"id": 2, "text": "B", "done": True}],
                "nums": [1, 2, 3],
            }
        )
    )
    flush()
    assert store["items"][0] is first
    assert store["items"][1].text == "B"
    assert memo() == "a"
    assert len(runs) == 1

    set_store(reconcile({"items": [{"id": 1, "text": "A", "done": False}]}))
    flush()
    assert store["items"][0] is first
    assert memo() == "A"
    assert len(runs) == 2


def test_reconcile_adds_removes_and_reorders_items(wyb):
    store, set_store = create_store({"items": [{"id": 1, "v": 1}, {"id": 2, "v": 2}]})
    second = store["items"][1]
    set_store(reconcile({"items": [{"id": 2, "v": 2}, {"id": 3, "v": 3}]}))
    flush()
    raw = snapshot(store)["items"]
    assert [i["id"] for i in raw] == [2, 3]
    assert store["items"][0] is second
    assert store["items"][1].v == 3
    assert len(store["items"]) == 2


def test_reconcile_removes_missing_dict_keys(wyb):
    store, set_store = create_store({"a": 1, "b": 2})
    set_store(reconcile({"a": 1}))
    flush()
    assert snapshot(store) == {"a": 1}
    assert "b" not in store


def test_reconcile_without_key_replaces_positionally(wyb):
    store, set_store = create_store({"items": [{"id": 1, "v": 1}]})
    first = store["items"][0]
    set_store(reconcile({"items": [{"id": 1, "v": 1}]}, key=None))
    flush()
    assert store["items"][0] == first
    assert store["items"][0] is not first


def test_reconcile_custom_key(wyb):
    store, set_store = create_store([{"slug": "x", "n": 1}, {"slug": "y", "n": 2}])
    x = store[0]
    set_store(reconcile([{"slug": "y", "n": 20}, {"slug": "x", "n": 1}], key="slug"))
    flush()
    assert store[1] is x
    assert store[0].n == 20


# ---------------------------------------------------------------------------
# Fine-grained tracking
# ---------------------------------------------------------------------------


def test_memo_tracks_only_its_path(wyb):
    store, set_store = _sample()
    memo, runs = _counting_memo(lambda: store.user.name)
    assert memo() == "Ada"
    assert len(runs) == 1

    set_store(lambda s: setattr(s.user, "age", 37))
    set_store(lambda s: setattr(s, "count", 1))
    flush()
    assert memo() == "Ada"
    assert len(runs) == 1

    set_store(lambda s: setattr(s.user, "name", "Grace"))
    flush()
    assert memo() == "Grace"
    assert len(runs) == 2


def test_memo_not_rerun_when_same_value_written(wyb):
    store, set_store = _sample()
    memo, runs = _counting_memo(lambda: store.count)
    assert memo() == 0
    set_store(lambda s: setattr(s, "count", 0))
    flush()
    assert memo() == 0
    assert len(runs) == 1


def test_memo_tracks_list_length(wyb):
    store, set_store = _sample()
    memo, runs = _counting_memo(lambda: len(store["items"]))
    assert memo() == 2

    set_store(lambda s: setattr(s["items"][0], "done", True))
    flush()
    assert memo() == 2
    assert len(runs) == 1

    set_store(lambda s: s["items"].append({"id": 3, "text": "c", "done": False}))
    flush()
    assert memo() == 3
    assert len(runs) == 2

    def pop_last(s):
        # A bare ``lambda s: s["items"].pop()`` would return the popped dict, which the
        # setter would merge in as replacement state.
        s["items"].pop()

    set_store(pop_last)
    flush()
    assert memo() == 2
    assert len(runs) == 3


def test_memo_tracks_iteration(wyb):
    store, set_store = _sample()
    memo, runs = _counting_memo(lambda: list(store.nums))
    assert memo() == [1, 2, 3]

    set_store(lambda s: s.nums.__setitem__(1, 20))
    flush()
    assert memo() == [1, 20, 3]
    assert len(runs) == 2

    set_store(lambda s: s.nums.append(4))
    flush()
    assert memo() == [1, 20, 3, 4]
    assert len(runs) == 3

    set_store(lambda s: setattr(s, "count", 5))
    flush()
    assert len(runs) == 3


def test_memo_tracks_one_list_item_field(wyb):
    store, set_store = _sample()
    memo, runs = _counting_memo(lambda: store["items"][0].done)
    assert memo() is False

    set_store(lambda s: setattr(s["items"][1], "done", False))
    flush()
    assert memo() is False
    assert len(runs) == 1

    set_store(lambda s: setattr(s["items"][0], "done", True))
    flush()
    assert memo() is True
    assert len(runs) == 2


def test_memo_tracks_membership_and_dict_len(wyb):
    store, set_store = create_store({"a": 1})
    memo, runs = _counting_memo(lambda: ("b" in store, len(store)))
    assert memo() == (False, 1)
    set_store(lambda s: setattr(s, "b", 2))
    flush()
    assert memo() == (True, 2)
    assert len(runs) == 2


def test_effect_first_run_deferred_and_reruns_on_change(wyb):
    store, set_store = _sample()
    log = []
    create_effect(lambda: store.count, lambda v: log.append(v))
    assert log == []
    flush()
    assert log == [0]

    set_store(lambda s: setattr(s, "count", 1))
    assert log == [0]
    flush()
    assert log == [0, 1]

    set_store(lambda s: setattr(s.user, "name", "Grace"))
    flush()
    assert log == [0, 1]


def test_single_form_effect_tracks_nested_paths(wyb):
    store, set_store = _sample()
    log = []
    create_tracked_effect(lambda: log.append((store.user.name, len(store.nums))))
    flush()
    assert log == [("Ada", 3)]

    set_store(lambda s: s.nums.append(4))
    flush()
    assert log == [("Ada", 3), ("Ada", 4)]


def test_effect_disposed_with_root_stops_tracking(wyb):
    store, set_store = _sample()
    log = []

    def setup(dispose):
        create_effect(lambda: store.count, lambda v: log.append(v))
        return dispose

    dispose = create_root(setup)
    flush()
    assert log == [0]
    dispose()
    set_store(lambda s: setattr(s, "count", 1))
    flush()
    assert log == [0]


def test_untracked_reads_do_not_subscribe(wyb):
    store, set_store = _sample()
    memo, runs = _counting_memo(lambda: untrack(lambda: store.count))
    assert memo() == 0
    set_store(lambda s: setattr(s, "count", 3))
    flush()
    assert memo() == 0
    assert len(runs) == 1


# ---------------------------------------------------------------------------
# snapshot / deep
# ---------------------------------------------------------------------------


def test_snapshot_returns_plain_data(wyb):
    initial = {"count": 0, "user": {"name": "Ada"}, "nums": [1, 2]}
    store, _ = create_store(initial)
    raw = snapshot(store)
    assert raw == initial
    assert raw is not initial
    assert type(raw) is dict
    assert type(raw["user"]) is dict
    assert type(snapshot(store.nums)) is list
    assert snapshot(store.user) == initial["user"]
    assert snapshot(store.user) is not initial["user"]
    assert snapshot(42) == 42


def test_snapshot_is_untracked(wyb):
    store, set_store = _sample()
    memo, runs = _counting_memo(lambda: snapshot(store)["count"])
    assert memo() == 0
    set_store(lambda s: setattr(s, "count", 7))
    flush()
    assert memo() == 0
    assert len(runs) == 1
    assert snapshot(store)["count"] == 7


def test_deep_returns_plain_copy(wyb):
    store, _ = _sample()
    copy_ = deep(store)
    assert copy_ == snapshot(store)
    assert copy_ is not snapshot(store)
    assert copy_["user"] is not snapshot(store)["user"]
    assert type(copy_["items"]) is list
    copy_["user"]["name"] = "Mutated"
    assert store.user.name == "Ada"
    assert deep(5) == 5


def test_deep_tracks_nested_changes(wyb):
    store, set_store = _sample()
    memo, runs = _counting_memo(lambda: deep(store)["items"][1]["text"])
    assert memo() == "b"

    set_store(lambda s: setattr(s["items"][0], "done", True))
    flush()
    assert memo() == "b"
    assert len(runs) == 2

    set_store(lambda s: setattr(s["items"][1], "text", "B"))
    flush()
    assert memo() == "B"
    assert len(runs) == 3


def test_deep_on_nested_proxy(wyb):
    store, set_store = _sample()
    memo, runs = _counting_memo(lambda: deep(store.user))
    assert memo() == {"name": "Ada", "age": 36}
    assert type(memo()) is dict

    set_store(lambda s: setattr(s.user, "age", 37))
    flush()
    assert memo() == {"name": "Ada", "age": 37}
    assert len(runs) == 2

    log = []
    create_effect(lambda: deep(store.nums), lambda d: log.append(d))
    flush()
    set_store(lambda s: s.nums.append(4))
    flush()
    assert log == [[1, 2, 3], [1, 2, 3, 4]]


# ---------------------------------------------------------------------------
# Derived stores and projections
# ---------------------------------------------------------------------------


def test_derived_store_draft_form_recomputes(wyb):
    n, set_n = create_signal(2)
    stats, _ = create_store(lambda d: d.update({"double": n() * 2}), {"double": 0})
    flush()
    assert stats.double == 4
    set_n(5)
    flush()
    assert stats.double == 10


def test_derived_store_zero_arg_form_reconciles(wyb):
    items, set_items = create_signal([{"id": 1, "v": 1}])
    mirror, _ = create_store(lambda: items(), [])
    flush()
    assert snapshot(mirror) == [{"id": 1, "v": 1}]
    first = mirror[0]

    set_items([{"id": 1, "v": 1}, {"id": 2, "v": 3}])
    flush()
    assert snapshot(mirror) == [{"id": 1, "v": 1}, {"id": 2, "v": 3}]
    assert mirror[0] is first
    assert mirror[1].v == 3


def test_derived_store_is_fine_grained(wyb):
    a, set_a = create_signal(1)
    b, set_b = create_signal(1)
    derived, _ = create_store(lambda d: d.update({"a": a(), "b": b()}), {"a": 0, "b": 0})
    flush()
    memo, runs = _counting_memo(lambda: derived.a)
    assert memo() == 1

    set_b(2)
    flush()
    assert derived.b == 2
    assert memo() == 1
    assert len(runs) == 1

    set_a(3)
    flush()
    assert memo() == 3
    assert len(runs) == 2


def test_create_projection_tracks_sources(wyb):
    sel, set_sel = create_signal(1)
    proj = create_projection(lambda d: d.update({"selected": sel()}), {"selected": None})
    flush()
    assert proj.selected == 1
    set_sel(7)
    flush()
    assert proj.selected == 7


def test_create_projection_zero_arg_and_read_only(wyb):
    sel, set_sel = create_signal("x")
    proj = create_projection(lambda: {"selected": sel()}, {"selected": None})
    flush()
    assert proj.selected == "x"
    set_sel("y")
    flush()
    assert proj.selected == "y"
    with pytest.raises(AttributeError):
        proj.selected = "z"
    with pytest.raises(TypeError):
        proj["selected"] = "z"


def test_projection_from_store_source(wyb):
    store, set_store = _sample()
    proj = create_projection(lambda d: d.update({"open": sum(1 for t in store["items"] if not t.done)}), {"open": 0})
    flush()
    assert proj.open == 1
    set_store(lambda s: setattr(s["items"][1], "done", False))
    flush()
    assert proj.open == 2


# ---------------------------------------------------------------------------
# Optimistic stores
# ---------------------------------------------------------------------------


def test_optimistic_store_value_form_applies_writes(wyb):
    shown, set_shown = create_optimistic_store({"n": 0, "items": []})
    assert shown.n == 0

    def edit(s):
        s.n = 1
        s["items"].append("x")

    set_shown(edit)
    flush()
    assert shown.n == 1
    assert list(shown["items"]) == ["x"]
    assert snapshot(shown) == {"n": 1, "items": ["x"]}


def test_optimistic_store_value_form_reverts_when_action_settles(wyb):
    async def main():
        shown, set_shown = create_optimistic_store({"n": 0})
        gate = asyncio.Event()

        @action
        async def bump():
            set_shown(lambda s: setattr(s, "n", 1))
            await gate.wait()

        bump()
        flush()
        assert shown.n == 1
        assert bump.pending() is True
        gate.set()
        await asyncio.sleep(0.01)
        flush()
        assert shown.n == 0
        assert bump.pending() is False

    asyncio.run(main())


def test_optimistic_store_derived_form_reverts_to_source(wyb):
    async def main():
        todos, set_todos = create_store({"items": []})
        shown, set_shown = create_optimistic_store(lambda: deep(todos)["items"], [])
        flush()
        assert snapshot(shown) == []
        gate = asyncio.Event()

        @action
        async def add(title):
            set_shown(lambda s: s.append({"id": 99, "title": title, "saving": True}))
            await gate.wait()
            set_todos(lambda s: s["items"].append({"id": 1, "title": title}))

        add("x")
        flush()
        assert len(shown) == 1
        assert shown[0].saving is True
        gate.set()
        await asyncio.sleep(0.01)
        flush()
        assert snapshot(shown) == [{"id": 1, "title": "x"}]

    asyncio.run(main())


def test_optimistic_store_derived_form_follows_source_changes(wyb):
    base, set_base = create_signal({"n": 1})
    shown, _ = create_optimistic_store(lambda: base(), {"n": 0})
    flush()
    assert shown.n == 1
    set_base({"n": 2})
    flush()
    assert shown.n == 2


# ---------------------------------------------------------------------------
# Dev-mode guards
# ---------------------------------------------------------------------------


def test_write_inside_memo_raises_write_in_scope_error(wyb, monkeypatch):
    monkeypatch.setattr(_warnings, "DEV_MODE", True)
    store, set_store = _sample()

    def compute():
        store.count
        set_store(lambda s: setattr(s, "count", 1))

    memo = create_memo(compute)
    with pytest.raises(WriteInScopeError):
        memo()


def test_write_inside_effect_compute_routes_to_error_handler(wyb, monkeypatch):
    monkeypatch.setattr(_warnings, "DEV_MODE", True)
    store, set_store = _sample()
    errs = []
    create_tracked_effect(lambda: (store.count, set_store(lambda s: None)), error=lambda e: errs.append(e))
    flush()
    assert len(errs) == 1
    assert isinstance(errs[0], WriteInScopeError)


def test_write_from_effect_apply_stage_is_allowed(wyb, monkeypatch):
    monkeypatch.setattr(_warnings, "DEV_MODE", True)
    store, set_store = _sample()
    create_effect(lambda: store.count, lambda v: set_store(lambda s: setattr(s, "doubled", v * 2)))
    flush()
    assert store.doubled == 0
    set_store(lambda s: setattr(s, "count", 4))
    flush()
    assert store.doubled == 8
