"""Typed Props instances, RawProps, merge/omit, children(), map_array, repeat, and projection selection."""

from collections.abc import Callable

import pytest

from wybthon.reactivity import (
    Prop,
    Props,
    children,
    create_effect,
    create_memo,
    create_root,
    create_signal,
    flush,
    map_array,
    merge,
    omit,
    on_cleanup,
    prop,
    repeat,
    untrack,
)
from wybthon.reactivity._props import RawProps
from wybthon.store import create_projection

# ---------------------------------------------------------------------------
# Typed Props instances
# ---------------------------------------------------------------------------


class NameProps(Props):
    name: Prop[str]
    greeting: Prop[str] = prop(default="hello")
    tags: Prop[list[str]] = prop(default_factory=list)
    on_click: Callable[..., None] | None = None
    size: int = 1


def test_prop_field_reads_return_one_cached_accessor(wyb):
    props = NameProps(name="Ada")
    assert props.name is props.name
    assert props.name() == "Ada"
    assert props.name.peek() == "Ada"
    assert isinstance(NameProps.name, Prop)
    assert repr(NameProps.name) == "Prop('name')"


def test_prop_fields_unwrap_accessors_and_zero_arg_callables(wyb):
    name, set_name = create_signal("Ada")
    props = NameProps(name=name, greeting=lambda: "hi")
    assert props.name() == "Ada"
    assert props.greeting() == "hi"
    set_name("Grace")
    flush()
    assert props.name() == "Grace"


def test_plain_fields_return_the_value_as_passed(wyb):
    handler = lambda e: None  # noqa: E731
    zero_arg = lambda: "never called"  # noqa: E731
    props = NameProps(name="x", on_click=handler)
    assert props.on_click is handler
    assert NameProps(name="x", on_click=zero_arg).on_click is zero_arg
    assert NameProps(name="x").on_click is None
    assert props.size == 1


def test_prop_defaults_and_default_factory(wyb):
    a = NameProps(name="a")
    b = NameProps(name="b")
    assert a.greeting() == "hello"
    assert a.tags() == [] and a.tags() is not b.tags()
    assert NameProps._wyb_required == frozenset({"name"})
    assert repr(a) == "NameProps({'name': 'a'})"


def test_props_update_pushes_new_values_into_live_accessors(wyb):
    props = NameProps(name="Ada")
    seen: list[str] = []
    create_root(lambda d: create_effect(props.greeting, lambda v: seen.append(v)))
    flush()
    props._wyb_update({"name": "Ada", "greeting": "hey"})
    flush()
    assert seen == ["hello", "hey"]
    # An omitted prop falls back to its default.
    props._wyb_update({"name": "Ada"})
    flush()
    assert seen == ["hello", "hey", "hello"]


def test_props_tracked_read_subscribes_memo(wyb):
    class N(Props):
        n: Prop[int]

    props = N(n=1)
    doubled = create_memo(lambda: props.n() * 2)
    assert doubled() == 2
    props._wyb_update({"n": 3})
    flush()
    assert doubled() == 6


def test_props_instances_reject_item_syntax(wyb):
    with pytest.raises(TypeError, match="don't take children"):
        NameProps(name="x")["child"]


# ---------------------------------------------------------------------------
# RawProps (framework-internal function tags)
# ---------------------------------------------------------------------------


def test_raw_props_attribute_and_item_access_return_the_same_accessor(wyb):
    props = RawProps({"name": "Ada"})
    assert props.name is props["name"]
    assert props.name() == "Ada"
    assert props.name.peek() == "Ada"


def test_raw_props_raw_returns_the_value_as_passed(wyb):
    name, _ = create_signal("Ada")
    handler = lambda e: None  # noqa: E731
    props = RawProps({"name": name, "on_click": handler})
    assert props.raw("name") is name
    assert props.raw("on_click") is handler
    assert props.name() == "Ada"


def test_raw_props_defaults_and_missing(wyb):
    props = RawProps({"a": 1}, defaults={"b": 2})
    assert props.a() == 1
    assert props.b() == 2
    assert props.c() is None
    assert "a" in props and "b" in props and "c" not in props
    assert list(props) == ["a", "b"]
    assert len(props) == 2
    assert props.get("missing", "fallback") == "fallback"
    assert props.get("b")() == 2


def test_raw_props_update_pushes_new_values(wyb):
    props = RawProps({"n": 1})
    seen: list[int] = []
    create_root(lambda d: create_effect(props.n, lambda v: seen.append(v)))
    flush()
    props._wyb_update({"n": 2})
    flush()
    assert seen == [1, 2]
    props._wyb_update({})
    flush()
    assert seen == [1, 2, None]


# ---------------------------------------------------------------------------
# merge / omit
# ---------------------------------------------------------------------------


class ShapeProps(Props):
    size: Prop[int] = prop(default=0)
    color: Prop[str] = prop(default="black")


def test_merge_later_sources_win_and_stay_reactive(wyb):
    color, set_color = create_signal("red")
    props = ShapeProps(size=1, color=color)
    merged = merge({"size": 0, "shape": "circle"}, props)
    assert merged["size"]() == 1
    assert merged["shape"]() == "circle"
    assert merged["color"]() == "red"
    set_color("blue")
    flush()
    assert merged["color"]() == "blue"
    assert merged.color() == "blue"
    assert set(merged) == {"size", "shape", "color"}


def test_merge_skips_none_sources_but_explicit_none_values_override(wyb):
    merged = merge({"a": 1}, None, lambda: {"b": 2})
    assert merged["a"]() == 1
    assert merged["b"]() == 2
    assert merge({"a": 1}, {"a": None})["a"]() is None


def test_merge_lets_props_override_only_what_the_parent_passed(wyb):
    # As in Solid, defaults merged in first apply unless the parent passed the key.
    assert merge({"color": "red"}, ShapeProps())["color"]() == "red"
    assert merge({"color": "red"}, ShapeProps(color="blue"))["color"]() == "blue"
    assert merge(ShapeProps(), {"color": "red"})["color"]() == "red"


def test_omit_hides_keys(wyb):
    props = ShapeProps(size=2, color="green")
    rest = omit(props, "size")
    assert set(rest) == {"color"}
    assert rest["color"]() == "green"
    assert "size" not in rest
    assert {k: rest[k]() for k in rest} == {"color": "green"}
    assert rest["size"]() is None


def test_omit_accepts_a_predicate(wyb):
    rest = omit({"on_click": 1, "on_input": 2, "id": "x", "title": "t"}, lambda key: key.startswith("on_"))
    assert sorted(rest) == ["id", "title"]
    assert rest["id"]() == "x"
    # Handler props pass through as values (never reactive bindings); omitted ones are None.
    assert rest["on_click"] is None
    nested = omit(rest, lambda key: key == "title")
    assert list(nested) == ["id"]


def test_omit_stays_reactive(wyb):
    color, set_color = create_signal("red")
    rest = omit(ShapeProps(color=color), "size")
    seen: list[str] = []
    create_root(lambda d: create_effect(rest["color"], lambda v: seen.append(v)))
    flush()
    set_color("blue")
    flush()
    assert seen == ["red", "blue"]
    assert rest["color"].peek() == "blue"


# ---------------------------------------------------------------------------
# children()
# ---------------------------------------------------------------------------


def test_children_flattens_and_drops_none(wyb):
    kids, set_kids = create_signal(["a", None, ["b", ["c"]]])
    resolved = children(kids)
    assert resolved() == ["a", "b", "c"]
    set_kids("solo")
    flush()
    assert resolved() == "solo"
    assert resolved.to_array() == ["solo"]
    set_kids(None)
    flush()
    assert resolved() == []
    assert resolved.to_array() == []


def test_children_resolves_nested_accessors_and_drops_booleans(wyb):
    flag, set_flag = create_signal(False)
    inner, _ = create_signal(["x", None])
    resolved = children(lambda: [True, "a", inner, lambda: "b" if flag() else False, (("c",),)])
    assert resolved.to_array() == ["a", "x", "c"]
    set_flag(True)
    flush()
    assert resolved.to_array() == ["a", "x", "b", "c"]


# ---------------------------------------------------------------------------
# map_array
# ---------------------------------------------------------------------------


def test_map_array_identity_keeps_rows_and_updates_index(wyb):
    a, b, c = {"id": "a"}, {"id": "b"}, {"id": "c"}
    items, set_items = create_signal([a, b])
    created: list[str] = []
    disposed: list[str] = []

    def row(item, index):
        created.append(item["id"])
        on_cleanup(lambda: disposed.append(item["id"]))
        return (item["id"], index)

    mapped = create_root(lambda d: map_array(items, row))
    rows = mapped()
    assert [r[0] for r in rows] == ["a", "b"]
    assert [r[1]() for r in rows] == [0, 1]
    set_items([b, c, a])
    flush()
    rows2 = mapped()
    assert [r[0] for r in rows2] == ["b", "c", "a"]
    assert [r[1]() for r in rows2] == [0, 1, 2]
    assert created == ["a", "b", "c"]
    assert disposed == []
    assert rows2[0] is rows[1] and rows2[2] is rows[0]
    set_items([c])
    flush()
    mapped()
    assert sorted(disposed) == ["a", "b"]


def test_map_array_identity_matches_scalars_by_value(wyb):
    items, set_items = create_signal([1, 2, 3])
    created: list[int] = []
    mapped = create_root(lambda d: map_array(items, lambda item, i: (created.append(item), item * 10)[1]))
    assert mapped() == [10, 20, 30]
    set_items([3, 2, 1, 4])
    flush()
    assert mapped() == [30, 20, 10, 40]
    assert created == [1, 2, 3, 4]


def test_map_array_positional_reuses_rows_and_updates_item(wyb):
    items, set_items = create_signal(["a", "b"])
    created: list[int] = []

    def row(item, index):
        created.append(index)
        return create_memo(lambda: f"{index}:{item()}")

    mapped = create_root(lambda d: map_array(items, row, keyed=False))
    assert [m() for m in mapped()] == ["0:a", "1:b"]
    set_items(["x", "y", "z"])
    flush()
    assert [m() for m in mapped()] == ["0:x", "1:y", "2:z"]
    assert created == [0, 1, 2]
    set_items(["q"])
    flush()
    assert [m() for m in mapped()] == ["0:q"]


def test_map_array_keyed_by_function_updates_item_and_index(wyb):
    items, set_items = create_signal([{"id": 1, "t": "a"}, {"id": 2, "t": "b"}])
    created: list[int] = []

    def row(item, index):
        created.append(item()["id"])
        return create_memo(lambda: f"{index()}:{item()['t']}")

    mapped = create_root(lambda d: map_array(items, row, keyed=lambda x: x["id"]))
    assert [m() for m in mapped()] == ["0:a", "1:b"]
    set_items([{"id": 2, "t": "B"}, {"id": 1, "t": "A"}, {"id": 3, "t": "c"}])
    flush()
    assert [m() for m in mapped()] == ["0:B", "1:A", "2:c"]
    assert created == [1, 2, 3]


def test_map_array_fallback_when_empty(wyb):
    items, set_items = create_signal([])
    mapped = create_root(lambda d: map_array(items, lambda item, i: item, fallback=lambda: "empty"))
    assert mapped() == ["empty"]
    set_items([1])
    flush()
    assert mapped() == [1]
    set_items(None)
    flush()
    assert mapped() == ["empty"]


def test_map_array_rows_run_untracked(wyb):
    items, _ = create_signal([1])
    other, set_other = create_signal(0)
    runs: list[int] = []

    def row(item, index):
        runs.append(other())
        return item

    mapped = create_root(lambda d: map_array(items, row))
    mapped()
    set_other(1)
    flush()
    mapped()
    assert runs == [0]


def test_map_array_disposes_rows_with_owner(wyb):
    items, _ = create_signal([1, 2])
    disposed: list[int] = []
    disposers: list = []

    def build(dispose):
        disposers.append(dispose)
        return map_array(items, lambda item, i: (on_cleanup(lambda: disposed.append(item)), item)[1])

    mapped = create_root(build)
    mapped()
    disposers[0]()
    assert sorted(disposed) == [1, 2]


# ---------------------------------------------------------------------------
# repeat
# ---------------------------------------------------------------------------


def test_repeat_maps_only_new_slots_and_disposes_removed_ones(wyb):
    count, set_count = create_signal(2)
    created: list[int] = []
    disposed: list[int] = []

    def row(i: int) -> str:
        created.append(i)
        on_cleanup(lambda: disposed.append(i))
        return f"row{i}"

    rows = create_root(lambda d: repeat(count, row))
    assert rows() == ["row0", "row1"]
    set_count(4)
    flush()
    assert rows() == ["row0", "row1", "row2", "row3"]
    assert created == [0, 1, 2, 3]
    set_count(1)
    flush()
    assert rows() == ["row0"]
    assert sorted(disposed) == [1, 2, 3]


def test_repeat_start_offset_and_fallback(wyb):
    count, set_count = create_signal(0)
    start, set_start = create_signal(5)
    rows = create_root(lambda d: repeat(count, lambda i: i, start=start, fallback=lambda: "none"))
    assert rows() == ["none"]
    set_count(2)
    flush()
    assert rows() == [5, 6]
    set_start(10)
    flush()
    assert rows() == [10, 11]
    assert create_root(lambda d: repeat(3, lambda i: i * 2))() == [0, 2, 4]


# ---------------------------------------------------------------------------
# Selection with create_projection (the create_selector replacement)
# ---------------------------------------------------------------------------


def test_projection_selection_notifies_only_affected_keys(wyb):
    selected, set_selected = create_signal(1)
    is_selected = create_root(lambda d: create_projection(lambda: {} if selected() is None else {selected(): True}))
    runs: dict[int, int] = {1: 0, 2: 0, 3: 0}
    memos = {}
    for key in (1, 2, 3):

        def make(k: int):
            def compute() -> bool:
                runs[k] += 1
                return bool(is_selected.get(k))

            return compute

        memos[key] = create_root(lambda d, key=key: create_memo(make(key)))
        create_root(lambda d, key=key: create_effect(memos[key], lambda v: None))
    flush()
    assert [memos[k]() for k in (1, 2, 3)] == [True, False, False]
    assert runs == {1: 1, 2: 1, 3: 1}
    set_selected(2)
    flush()
    assert [untrack(memos[k]) for k in (1, 2, 3)] == [False, True, False]
    assert runs == {1: 2, 2: 2, 3: 1}
    set_selected(None)
    flush()
    assert [untrack(memos[k]) for k in (1, 2, 3)] == [False, False, False]
    assert runs == {1: 2, 2: 3, 3: 1}
