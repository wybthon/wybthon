"""Tests for reactive merge_props and split_props proxy objects."""

import time

from wybthon.reactivity import (
    _MergedProps,
    _SplitProps,
    create_effect,
    create_root,
    create_signal,
    merge_props,
    split_props,
)

# ---------------------------------------------------------------------------
# merge_props — proxy basics
# ---------------------------------------------------------------------------


def test_merge_props_returns_proxy():
    result = merge_props({"a": 1})
    assert isinstance(result, _MergedProps)


def test_merge_props_basic():
    result = merge_props({"a": 1}, {"b": 2})
    assert result == {"a": 1, "b": 2}


def test_merge_props_override():
    result = merge_props({"a": 1, "b": 2}, {"b": 3})
    assert result == {"a": 1, "b": 3}


def test_merge_props_none_source():
    result = merge_props({"a": 1}, None, {"c": 3})
    assert result == {"a": 1, "c": 3}


def test_merge_props_getitem():
    result = merge_props({"x": 10}, {"y": 20})
    assert result["x"] == 10
    assert result["y"] == 20


def test_merge_props_get():
    result = merge_props({"a": 1})
    assert result.get("a") == 1
    assert result.get("missing", 42) == 42


def test_merge_props_contains():
    result = merge_props({"a": 1}, {"b": 2})
    assert "a" in result
    assert "b" in result
    assert "c" not in result


def test_merge_props_iter():
    result = merge_props({"a": 1}, {"b": 2})
    keys = list(result)
    assert sorted(keys) == ["a", "b"]


def test_merge_props_len():
    result = merge_props({"a": 1}, {"b": 2})
    assert len(result) == 2


def test_merge_props_items():
    result = merge_props({"a": 1}, {"b": 2})
    assert dict(result.items()) == {"a": 1, "b": 2}


def test_merge_props_keys():
    result = merge_props({"a": 1}, {"b": 2})
    assert sorted(result.keys()) == ["a", "b"]


def test_merge_props_values():
    result = merge_props({"a": 1}, {"b": 2})
    assert sorted(result.values()) == [1, 2]


def test_merge_props_repr():
    result = merge_props({"a": 1})
    assert "MergedProps" in repr(result)


# ---------------------------------------------------------------------------
# merge_props — reactive (callable sources)
# ---------------------------------------------------------------------------


def test_merge_props_callable_source():
    defaults = {"size": "md"}
    dynamic, set_dynamic = create_signal({"color": "red"})
    merged = merge_props(defaults, dynamic)

    assert merged["size"] == "md"
    assert merged["color"] == "red"

    set_dynamic({"color": "blue"})
    assert merged["color"] == "blue"


def test_merge_props_reactive_tracking():
    """Reading from a merged proxy inside an effect tracks the source signal."""
    defaults = {"a": 1}
    source, set_source = create_signal({"b": 2})
    merged = merge_props(defaults, source)
    log: list = []

    def body(dispose):
        create_effect(lambda: log.append(merged["b"]))
        return dispose

    dispose = create_root(body)
    assert log == [2]

    set_source({"b": 99})
    time.sleep(0.05)
    assert log[-1] == 99
    dispose()


def test_merge_props_override_with_callable():
    base = {"x": 1}
    overlay, set_overlay = create_signal({"x": 10})
    merged = merge_props(base, overlay)

    assert merged["x"] == 10

    set_overlay({"x": 20})
    assert merged["x"] == 20


# ---------------------------------------------------------------------------
# split_props — proxy basics
# ---------------------------------------------------------------------------


def test_split_props_returns_proxies():
    local, rest = split_props({"a": 1, "b": 2}, ["a"])
    assert isinstance(local, _SplitProps)
    assert isinstance(rest, _SplitProps)


def test_split_props_single_group():
    local, rest = split_props({"a": 1, "b": 2, "c": 3}, ["a", "b"])
    assert local == {"a": 1, "b": 2}
    assert rest == {"c": 3}


def test_split_props_multiple_groups():
    g1, g2, rest = split_props(
        {"a": 1, "b": 2, "c": 3, "d": 4},
        ["a", "b"],
        ["c"],
    )
    assert g1 == {"a": 1, "b": 2}
    assert g2 == {"c": 3}
    assert rest == {"d": 4}


def test_split_props_missing_key():
    local, rest = split_props({"a": 1}, ["a", "missing"])
    assert local == {"a": 1}
    assert rest == {}


def test_split_props_getitem():
    local, rest = split_props({"a": 1, "b": 2}, ["a"])
    assert local["a"] == 1
    assert rest["b"] == 2


def test_split_props_contains():
    local, rest = split_props({"a": 1, "b": 2}, ["a"])
    assert "a" in local
    assert "a" not in rest
    assert "b" in rest
    assert "b" not in local


def test_split_props_repr():
    local, _ = split_props({"a": 1}, ["a"])
    assert "SplitProps" in repr(local)


# ---------------------------------------------------------------------------
# split_props — reactive
# ---------------------------------------------------------------------------


def test_split_props_callable_source():
    source, set_source = create_signal({"a": 1, "b": 2, "c": 3})
    local, rest = split_props(source, ["a", "b"])

    assert local == {"a": 1, "b": 2}
    assert rest == {"c": 3}

    set_source({"a": 10, "b": 20, "c": 30})
    assert local == {"a": 10, "b": 20}
    assert rest == {"c": 30}


def test_split_props_reactive_tracking():
    """Reading from a split proxy inside an effect tracks the source signal."""
    source, set_source = create_signal({"x": 1, "y": 2})
    local, rest = split_props(source, ["x"])
    log: list = []

    def body(dispose):
        create_effect(lambda: log.append(local["x"]))
        return dispose

    dispose = create_root(body)
    assert log == [1]

    set_source({"x": 99, "y": 2})
    time.sleep(0.05)
    assert log[-1] == 99
    dispose()


# ---------------------------------------------------------------------------
# merge_props + split_props composition
# ---------------------------------------------------------------------------


def test_merge_then_split():
    defaults = {"size": "md", "color": "blue", "label": "ok"}
    overrides = {"color": "red"}
    merged = merge_props(defaults, overrides)
    local, rest = split_props(merged, ["color", "size"])

    assert local == {"color": "red", "size": "md"}
    assert rest == {"label": "ok"}


def test_split_then_merge():
    props = {"a": 1, "b": 2, "c": 3}
    local, rest = split_props(props, ["a"])
    merged = merge_props(rest, {"d": 4})

    assert "a" not in merged
    assert merged == {"b": 2, "c": 3, "d": 4}
