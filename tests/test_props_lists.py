"""Props mappings, prop defaults, merge/omit, children(), map_array, and create_selector."""

from __future__ import annotations

from wybthon.reactivity import (
    Prop,
    Props,
    children,
    create_effect,
    create_memo,
    create_root,
    create_selector,
    create_signal,
    flush,
    map_array,
    merge,
    omit,
    on_cleanup,
    prop,
    untrack,
)

# ---------------------------------------------------------------------------
# Props
# ---------------------------------------------------------------------------


def test_props_attribute_and_item_access_return_the_same_prop(wyb):
    props = Props({"name": "Ada"})
    assert isinstance(props.name, Prop)
    assert props.name is props["name"]
    assert props.name() == "Ada"
    assert props.name.peek() == "Ada"


def test_props_unwrap_accessors_and_zero_arg_callables(wyb):
    name, set_name = create_signal("Ada")
    props = Props({"name": name, "greeting": lambda: "hi"})
    assert props.name() == "Ada"
    assert props.greeting() == "hi"
    set_name("Grace")
    flush()
    assert props.name() == "Grace"


def test_props_raw_returns_the_value_as_passed(wyb):
    name, _ = create_signal("Ada")
    handler = lambda e: None  # noqa: E731
    props = Props({"name": name, "on_click": handler})
    assert props.raw("name") is name
    assert props.raw("on_click") is handler
    assert props.on_click() is handler


def test_props_defaults_and_missing(wyb):
    props = Props({"a": 1}, defaults={"b": 2})
    assert props.a() == 1
    assert props.b() == 2
    assert props.c() is None
    assert "a" in props and "b" in props and "c" not in props
    assert list(props) == ["a"]
    assert len(props) == 1
    assert props.snapshot() == {"a": 1, "b": 2}


def test_props_update_pushes_new_values_into_live_accessors(wyb):
    props = Props({"n": 1})
    seen: list[int] = []
    create_root(lambda d: create_effect(props.n, lambda v: seen.append(v)))
    flush()
    props._update({"n": 2})
    flush()
    assert seen == [1, 2]
    props._update({})
    flush()
    assert seen == [1, 2, None]


def test_prop_marker_and_default_value(wyb):
    marker = prop(5)
    assert isinstance(marker, Prop)
    assert marker() == 5
    assert marker.peek() == 5


def test_props_tracked_read_subscribes_memo(wyb):
    props = Props({"n": 1})
    doubled = create_memo(lambda: props.n() * 2)
    assert doubled() == 2
    props._update({"n": 3})
    flush()
    assert doubled() == 6


# ---------------------------------------------------------------------------
# merge / omit
# ---------------------------------------------------------------------------


def test_merge_later_sources_win_and_stay_reactive(wyb):
    color, set_color = create_signal("red")
    props = Props({"size": 1, "color": color})
    merged = merge({"size": 0, "shape": "circle"}, props)
    assert merged["size"]() == 1
    assert merged["shape"]() == "circle"
    assert merged["color"]() == "red"
    set_color("blue")
    flush()
    assert merged["color"]() == "blue"
    assert set(merged) == {"size", "shape", "color"}


def test_merge_skips_none_sources_but_explicit_none_values_override(wyb):
    merged = merge({"a": 1}, None, lambda: {"b": 2})
    assert merged["a"]() == 1
    assert merged["b"]() == 2
    assert merge({"a": 1}, {"a": None})["a"]() is None


def test_omit_hides_keys(wyb):
    props = Props({"a": 1, "b": 2, "c": 3})
    rest = omit(props, "a")
    assert set(rest) == {"b", "c"}
    assert rest["b"]() == 2
    assert "a" not in rest
    assert rest.snapshot() == {"b": 2, "c": 3}


# ---------------------------------------------------------------------------
# children()
# ---------------------------------------------------------------------------


def test_children_flattens_and_drops_none(wyb):
    kids, set_kids = create_signal(["a", None, ["b", ["c"]]])
    resolved = children(kids)
    assert resolved() == ["a", "b", "c"]
    set_kids("solo")
    flush()
    assert resolved() == ["solo"]
    set_kids(None)
    flush()
    assert resolved() == []


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
# create_selector
# ---------------------------------------------------------------------------


def test_create_selector_notifies_only_affected_keys(wyb):
    selected, set_selected = create_signal(1)
    is_selected = create_root(lambda d: create_selector(selected))
    runs: dict[int, int] = {1: 0, 2: 0, 3: 0}
    memos = {}
    for key in (1, 2, 3):

        def make(k: int):
            def compute() -> bool:
                runs[k] += 1
                return is_selected(k)

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
