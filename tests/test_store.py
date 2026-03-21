"""Tests for create_store, produce, and the batch(fn) enhancement."""

import time

import pytest

from wybthon.reactivity import batch, create_effect, create_signal, effect
from wybthon.store import create_store, produce

# --------------------------------------------------------------------------- #
# create_store basics
# --------------------------------------------------------------------------- #


class TestCreateStore:
    def test_basic_dict_store(self):
        store, set_store = create_store({"count": 0, "name": "Ada"})
        assert store.count == 0
        assert store.name == "Ada"

    def test_set_top_level_value(self):
        store, set_store = create_store({"count": 0})
        set_store("count", 5)
        assert store.count == 5

    def test_set_top_level_functional_update(self):
        store, set_store = create_store({"count": 10})
        set_store("count", lambda c: c + 1)
        assert store.count == 11

    def test_nested_dict_read(self):
        store, set_store = create_store({"user": {"name": "Ada", "age": 30}})
        assert store.user.name == "Ada"
        assert store.user.age == 30

    def test_nested_dict_set(self):
        store, set_store = create_store({"user": {"name": "Ada"}})
        set_store("user", "name", "Jane")
        assert store.user.name == "Jane"

    def test_list_access(self):
        store, set_store = create_store({"items": ["a", "b", "c"]})
        assert store.items[0] == "a"
        assert store.items[1] == "b"
        assert store.items[2] == "c"

    def test_list_length(self):
        store, set_store = create_store({"items": [1, 2, 3]})
        assert len(store.items) == 3

    def test_list_iteration(self):
        store, set_store = create_store({"items": ["x", "y", "z"]})
        result = list(store.items)
        assert result == ["x", "y", "z"]

    def test_list_contains(self):
        store, set_store = create_store({"items": [1, 2, 3]})
        assert 2 in store.items
        assert 9 not in store.items

    def test_nested_list_of_dicts(self):
        store, set_store = create_store(
            {
                "todos": [
                    {"id": 1, "text": "Learn Wybthon", "done": False},
                    {"id": 2, "text": "Build an app", "done": False},
                ]
            }
        )
        assert store.todos[0].text == "Learn Wybthon"
        assert store.todos[1].done is False

    def test_set_nested_list_item_property(self):
        store, set_store = create_store({"todos": [{"id": 1, "text": "Test", "done": False}]})
        set_store("todos", 0, "done", True)
        assert store.todos[0].done is True

    def test_store_repr(self):
        store, _ = create_store({"count": 0})
        r = repr(store)
        assert "count" in r

    def test_store_equality(self):
        store, _ = create_store({"a": 1})
        assert store == {"a": 1}

    def test_store_contains(self):
        store, _ = create_store({"a": 1, "b": 2})
        assert "a" in store
        assert "c" not in store

    def test_store_iter(self):
        store, _ = create_store({"a": 1, "b": 2})
        keys = list(store)
        assert "a" in keys
        assert "b" in keys

    def test_store_len(self):
        store, _ = create_store({"a": 1, "b": 2, "c": 3})
        assert len(store) == 3

    def test_store_getitem_string(self):
        store, _ = create_store({"key": "value"})
        assert store["key"] == "value"

    def test_store_read_only(self):
        store, _ = create_store({"count": 0})
        with pytest.raises(AttributeError, match="read-only"):
            store.count = 5

    def test_set_store_with_dict_arg(self):
        store, set_store = create_store({"a": 1, "b": 2})
        set_store({"a": 10, "b": 20})
        assert store.a == 10
        assert store.b == 20

    def test_set_store_no_args_raises(self):
        _, set_store = create_store({"a": 1})
        with pytest.raises(TypeError, match="requires at least one argument"):
            set_store()


# --------------------------------------------------------------------------- #
# Reactivity
# --------------------------------------------------------------------------- #


class TestStoreReactivity:
    def test_effect_tracks_store_read(self):
        store, set_store = create_store({"count": 0})
        seen = []

        def watcher():
            seen.append(store.count)

        eff = effect(watcher)
        assert seen == [0]

        set_store("count", 5)
        time.sleep(0.05)
        assert seen == [0, 5]
        eff.dispose()

    def test_effect_tracks_nested_read(self):
        store, set_store = create_store({"user": {"name": "Ada"}})
        seen = []

        def watcher():
            seen.append(store.user.name)

        eff = effect(watcher)
        assert seen == ["Ada"]

        set_store("user", "name", "Jane")
        time.sleep(0.05)
        assert seen == ["Ada", "Jane"]
        eff.dispose()

    def test_effect_tracks_list_item(self):
        store, set_store = create_store({"items": ["a", "b"]})
        seen = []

        def watcher():
            seen.append(store.items[0])

        eff = effect(watcher)
        assert seen == ["a"]

        set_store("items", 0, "z")
        time.sleep(0.05)
        assert seen == ["a", "z"]
        eff.dispose()

    def test_functional_update_triggers_effect(self):
        store, set_store = create_store({"count": 0})
        seen = []

        def watcher():
            seen.append(store.count)

        eff = effect(watcher)
        assert seen == [0]

        set_store("count", lambda c: c + 10)
        time.sleep(0.05)
        assert seen == [0, 10]
        eff.dispose()

    def test_effect_tracks_list_length(self):
        store, set_store = create_store({"items": [1, 2, 3]})
        seen = []

        def watcher():
            seen.append(len(store.items))

        eff = effect(watcher)
        assert seen == [3]

        set_store("items", lambda items: [*items, 4])
        time.sleep(0.05)
        assert seen[-1] == 4
        eff.dispose()

    def test_create_effect_with_store(self):
        store, set_store = create_store({"value": "hello"})
        log = []

        comp = create_effect(lambda: log.append(store.value))
        assert log == ["hello"]

        set_store("value", "world")
        time.sleep(0.05)
        assert log == ["hello", "world"]
        comp.dispose()


# --------------------------------------------------------------------------- #
# produce
# --------------------------------------------------------------------------- #


class TestProduce:
    def test_produce_setattr(self):
        store, set_store = create_store({"count": 0})
        set_store(produce(lambda s: setattr(s, "count", 42)))
        assert store.count == 42

    def test_produce_nested_setattr(self):
        store, set_store = create_store({"user": {"name": "Ada"}})
        set_store(produce(lambda s: setattr(s.user, "name", "Jane")))
        assert store.user.name == "Jane"

    def test_produce_list_append(self):
        store, set_store = create_store({"items": [1, 2]})
        set_store(produce(lambda s: s.items.append(3)))
        assert list(store.items) == [1, 2, 3]

    def test_produce_list_pop(self):
        store, set_store = create_store({"items": [1, 2, 3]})
        set_store(produce(lambda s: s.items.pop(-1)))
        assert list(store.items) == [1, 2]

    def test_produce_list_item_set(self):
        store, set_store = create_store({"items": ["a", "b", "c"]})
        set_store(produce(lambda s: s.items.__setitem__(1, "B")))
        assert store.items[1] == "B"

    def test_produce_nested_dict_in_list(self):
        store, set_store = create_store({"todos": [{"text": "Test", "done": False}]})
        set_store(produce(lambda s: setattr(s.todos[0], "done", True)))
        assert store.todos[0].done is True

    def test_produce_triggers_reactivity(self):
        store, set_store = create_store({"count": 0})
        seen = []

        eff = effect(lambda: seen.append(store.count))
        assert seen == [0]

        set_store(produce(lambda s: setattr(s, "count", 99)))
        time.sleep(0.05)
        assert seen == [0, 99]
        eff.dispose()

    def test_produce_multiple_mutations(self):
        store, set_store = create_store({"a": 1, "b": 2})

        def mutate(s):
            s.a = 10
            s.b = 20

        set_store(produce(mutate))
        assert store.a == 10
        assert store.b == 20

    def test_produce_pop_front_updates_indices(self):
        """Popping index 0 should shift all per-index values."""
        store, set_store = create_store({"items": [{"v": "A"}, {"v": "B"}, {"v": "C"}]})
        assert store.items[0].v == "A"

        set_store(produce(lambda s: s.items.pop(0)))
        assert len(store.items) == 2
        assert store.items[0].v == "B"
        assert store.items[1].v == "C"

    def test_produce_pop_middle_updates_indices(self):
        """Popping from the middle should shift subsequent indices."""
        store, set_store = create_store({"items": [{"v": "A"}, {"v": "B"}, {"v": "C"}, {"v": "D"}]})
        assert store.items[1].v == "B"

        set_store(produce(lambda s: s.items.pop(1)))
        assert len(store.items) == 3
        assert store.items[0].v == "A"
        assert store.items[1].v == "C"
        assert store.items[2].v == "D"

    def test_produce_pop_front_triggers_effect(self):
        """Effects reading list items should see correct values after pop(0)."""
        store, set_store = create_store({"items": [{"v": "A"}, {"v": "B"}, {"v": "C"}]})
        seen: list = []

        def watcher():
            seen.clear()
            for item in store.items:
                seen.append(item.v)

        eff = effect(watcher)
        assert seen == ["A", "B", "C"]

        set_store(produce(lambda s: s.items.pop(0)))
        time.sleep(0.05)
        assert seen == ["B", "C"]
        eff.dispose()

    def test_produce_append_then_pop_front(self):
        """Append followed by pop(0) should leave correct items."""
        store, set_store = create_store({"items": [{"v": "A"}]})
        assert store.items[0].v == "A"

        set_store(produce(lambda s: s.items.append({"v": "B"})))
        assert len(store.items) == 2
        assert store.items[1].v == "B"

        set_store(produce(lambda s: s.items.pop(0)))
        assert len(store.items) == 1
        assert store.items[0].v == "B"


# --------------------------------------------------------------------------- #
# batch(fn) enhancement
# --------------------------------------------------------------------------- #


class TestBatchFunction:
    def test_batch_with_function(self):
        count, set_count = create_signal(0)
        name, set_name = create_signal("old")
        seen = []

        eff = effect(lambda: seen.append((count(), name())))
        assert seen == [(0, "old")]

        def update():
            set_count(1)
            set_name("new")

        batch(update)
        assert seen == [(0, "old"), (1, "new")]
        eff.dispose()

    def test_batch_function_returns_value(self):
        result = batch(lambda: 42)
        assert result == 42

    def test_batch_context_manager_still_works(self):
        count, set_count = create_signal(0)
        seen = []

        eff = effect(lambda: seen.append(count()))
        assert seen == [0]

        with batch():
            set_count(1)
            set_count(2)
            set_count(3)
        time.sleep(0.05)
        assert seen[-1] == 3
        eff.dispose()

    def test_batch_none_returns_context_manager(self):
        ctx = batch()
        assert hasattr(ctx, "__enter__")
        assert hasattr(ctx, "__exit__")

    def test_batch_function_flushes_synchronously(self):
        """Effects should have run by the time batch(fn) returns."""
        a, set_a = create_signal(0)
        log = []
        eff = effect(lambda: log.append(a()))
        assert log == [0]

        batch(lambda: set_a(99))
        assert log == [0, 99]
        eff.dispose()


# --------------------------------------------------------------------------- #
# Edge cases
# --------------------------------------------------------------------------- #


class TestStoreEdgeCases:
    def test_deeply_nested(self):
        store, set_store = create_store({"a": {"b": {"c": {"d": 42}}}})
        assert store.a.b.c.d == 42
        set_store("a", "b", "c", "d", 100)
        assert store.a.b.c.d == 100

    def test_set_replaces_entire_nested_dict(self):
        store, set_store = create_store({"user": {"name": "Ada", "age": 30}})
        set_store("user", {"name": "Jane", "age": 25})
        assert store.user.name == "Jane"
        assert store.user.age == 25

    def test_set_replaces_entire_list(self):
        store, set_store = create_store({"items": [1, 2, 3]})
        set_store("items", [4, 5])
        assert list(store.items) == [4, 5]

    def test_none_values(self):
        store, _ = create_store({"nullable": None})
        assert store.nullable is None

    def test_boolean_values(self):
        store, set_store = create_store({"flag": False})
        assert store.flag is False
        set_store("flag", True)
        assert store.flag is True

    def test_numeric_values(self):
        store, set_store = create_store({"pi": 3.14})
        assert store.pi == 3.14
        set_store("pi", 3.14159)
        assert store.pi == 3.14159

    def test_list_proxy_repr(self):
        store, _ = create_store({"items": [1, 2]})
        r = repr(store.items)
        assert "1" in r and "2" in r

    def test_list_proxy_equality(self):
        store, _ = create_store({"items": [1, 2, 3]})
        assert store.items == [1, 2, 3]

    def test_callable_top_level_update(self):
        store, set_store = create_store({"count": 5})
        set_store(lambda raw: {"count": raw["count"] * 2})
        assert store.count == 10

    def test_produce_read_during_draft(self):
        """Draft reads should return current values."""
        store, set_store = create_store({"x": 10, "y": 20})
        captured = []

        def mutate(s):
            captured.append(s.x)
            s.y = s.x + 5

        set_store(produce(mutate))
        assert captured == [10]
        assert store.y == 15

    # ---- list replacement / pop correctness ---- #

    def test_functional_list_filter_removes_correct_item(self):
        """Filtering a list via functional update should remove the right item.

        Regression test for a bug where removing index 0 actually dropped the
        last item because child-node signals were not refreshed after the list
        reference was replaced.
        """
        store, set_store = create_store(
            {
                "todos": [
                    {"id": 1, "text": "first", "done": True},
                    {"id": 2, "text": "second", "done": False},
                    {"id": 3, "text": "third", "done": False},
                    {"id": 4, "text": "fourth", "done": False},
                ]
            }
        )

        assert store.todos[0].text == "first"

        set_store(
            "todos",
            lambda ts: [t for i, t in enumerate(ts) if i != 0],
        )

        assert len(store.todos) == 3
        assert store.todos[0].text == "second"
        assert store.todos[1].text == "third"
        assert store.todos[2].text == "fourth"

    def test_functional_list_filter_with_effect(self):
        """Effects tracking list items should see correct values after filter."""
        store, set_store = create_store(
            {
                "todos": [
                    {"id": 1, "text": "A"},
                    {"id": 2, "text": "B"},
                    {"id": 3, "text": "C"},
                ]
            }
        )
        texts: list = []

        def watcher():
            texts.clear()
            for item in store.todos:
                texts.append(item.text)

        eff = effect(watcher)
        assert texts == ["A", "B", "C"]

        set_store("todos", lambda ts: [t for t in ts if t["id"] != 1])
        time.sleep(0.05)
        assert texts == ["B", "C"]

        set_store("todos", lambda ts: [t for t in ts if t["id"] != 3])
        time.sleep(0.05)
        assert texts == ["B"]
        eff.dispose()

    def test_replace_list_with_scalars_after_nested_reads(self):
        """Replacing a list of dicts with scalars after reading nested props."""
        store, set_store = create_store({"items": [{"name": "A"}, {"name": "B"}]})
        assert store.items[0].name == "A"
        assert store.items[1].name == "B"

        set_store("items", [10, 20])
        assert store.items[0] == 10
        assert store.items[1] == 20

    def test_multiple_sequential_list_replacements(self):
        """Multiple list replacements with reads between each."""
        store, set_store = create_store({"items": [{"v": "A"}, {"v": "B"}, {"v": "C"}]})
        assert store.items[0].v == "A"

        set_store("items", lambda ts: [t for t in ts if t["v"] != "A"])
        assert store.items[0].v == "B"
        assert store.items[1].v == "C"

        set_store("items", lambda ts: [t for t in ts if t["v"] != "B"])
        assert len(store.items) == 1
        assert store.items[0].v == "C"

        set_store("items", lambda ts: [t for t in ts if t["v"] != "C"])
        assert len(store.items) == 0

    def test_replace_nested_dict_after_reading_children(self):
        """Replacing a nested dict should update child signals."""
        store, set_store = create_store({"user": {"name": "Ada", "address": {"city": "London"}}})
        assert store.user.address.city == "London"

        set_store("user", {"name": "Jane", "address": {"city": "Paris"}})
        assert store.user.name == "Jane"
        assert store.user.address.city == "Paris"

    def test_grow_and_shrink_list_repeatedly(self):
        """Grow then shrink a list multiple times."""
        store, set_store = create_store({"items": []})

        set_store("items", [1, 2, 3])
        assert list(store.items) == [1, 2, 3]

        set_store("items", [1])
        assert list(store.items) == [1]
        assert len(store.items) == 1

        set_store("items", [10, 20, 30, 40])
        assert list(store.items) == [10, 20, 30, 40]
        assert len(store.items) == 4
