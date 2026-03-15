"""Tests for reactive utilities (untrack, on, create_root, merge_props, split_props)."""

import time

from wybthon.reactivity import (
    create_effect,
    create_root,
    create_signal,
    effect,
    merge_props,
    on,
    signal,
    split_props,
    untrack,
)


def test_untrack_prevents_dependency():
    a = signal(0)
    b = signal(0)
    log = []

    def tracked():
        val_a = a.get()
        val_b = untrack(b.get)
        log.append((val_a, val_b))

    effect(tracked)
    assert log == [(0, 0)]

    b.set(10)
    time.sleep(0.05)
    assert log == [(0, 0)]

    a.set(1)
    time.sleep(0.05)
    assert log[-1] == (1, 10)


def test_untrack_returns_value():
    s = signal(42)
    result = untrack(s.get)
    assert result == 42


def test_on_single_dep():
    a = signal(0)
    log = []
    on(a.get, lambda v: log.append(v))
    assert log == [0]

    a.set(5)
    time.sleep(0.05)
    assert log[-1] == 5


def test_on_defer():
    a = signal(0)
    log = []
    on(a.get, lambda v: log.append(v), defer=True)
    assert log == []

    a.set(1)
    time.sleep(0.05)
    assert log == [1]


def test_on_multiple_deps():
    a = signal(1)
    b = signal(2)
    log = []
    on([a.get, b.get], lambda va, vb: log.append((va, vb)))
    assert log == [(1, 2)]

    a.set(10)
    time.sleep(0.05)
    assert log[-1] == (10, 2)


def test_merge_props_basic():
    result = merge_props({"a": 1}, {"b": 2})
    assert result == {"a": 1, "b": 2}


def test_merge_props_override():
    result = merge_props({"a": 1, "b": 2}, {"b": 3})
    assert result == {"a": 1, "b": 3}


def test_merge_props_none_source():
    result = merge_props({"a": 1}, None, {"c": 3})
    assert result == {"a": 1, "c": 3}


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


def test_create_root_runs_fn():
    result = create_root(lambda dispose: 42)
    assert result == 42


def test_create_root_dispose():
    disposed = [False]

    def inner(dispose):
        count, _ = create_signal(0)
        create_effect(lambda: count())
        dispose()
        disposed[0] = True
        return "ok"

    result = create_root(inner)
    assert result == "ok"
    assert disposed[0]
