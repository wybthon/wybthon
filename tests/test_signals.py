"""Signals, memos, effects, and ownership: the synchronous reactive core."""

from __future__ import annotations

import pytest

from wybthon import _warnings
from wybthon.reactivity import (
    Accessor,
    Memo,
    WriteInScopeError,
    create_effect,
    create_memo,
    create_render_effect,
    create_root,
    create_signal,
    create_tracked_effect,
    flush,
    get_owner,
    is_accessor,
    on_cleanup,
    run_with_owner,
    untrack,
)

# ---------------------------------------------------------------------------
# Signals
# ---------------------------------------------------------------------------


def test_signal_read_write_is_staged_until_flush(wyb):
    count, set_count = create_signal(0)
    assert isinstance(count, Accessor)
    assert count() == 0
    assert set_count(5) == 5
    assert count() == 0
    flush()
    assert count() == 5


def test_functional_update_sees_staged_value(wyb):
    count, set_count = create_signal(1)
    set_count(lambda n: n + 1)
    set_count(lambda n: n * 10)
    flush()
    assert count() == 20


def test_peek_reads_committed_value_untracked(wyb):
    count, set_count = create_signal(1)
    runs: list[int] = []
    memo = create_memo(lambda: (runs.append(1), count.peek())[1])
    assert memo() == 1
    set_count(2)
    flush()
    assert memo() == 1
    assert runs == [1]


def test_equal_writes_do_not_notify(wyb):
    count, set_count = create_signal(1)
    runs: list[int] = []
    memo = create_memo(lambda: (runs.append(count()), count())[1])
    memo()
    set_count(1)
    flush()
    memo()
    assert runs == [1]


def test_equals_false_always_notifies(wyb):
    value, set_value = create_signal([1], equals=False)
    runs: list[int] = []
    memo = create_memo(lambda: (runs.append(1), value())[1])
    memo()
    set_value(value.peek())
    flush()
    memo()
    assert runs == [1, 1]


def test_custom_equals(wyb):
    value, set_value = create_signal({"n": 1}, equals=lambda a, b: a["n"] == b["n"])
    runs: list[int] = []
    memo = create_memo(lambda: (runs.append(1), value()["n"])[1])
    memo()
    set_value({"n": 1})
    flush()
    memo()
    assert runs == [1]
    set_value({"n": 2})
    flush()
    assert memo() == 2


def test_storing_a_callable_requires_wrapping(wyb):
    fn, set_fn = create_signal(None)
    target = object()
    set_fn(lambda _: target)
    flush()
    assert fn() is target


def test_writable_derived_signal_function_form(wyb):
    count, set_count = create_signal(2)
    doubled, set_doubled = create_signal(lambda: count() * 2)
    assert doubled() == 4
    set_doubled(99)
    flush()
    assert doubled() == 99
    set_count(5)
    flush()
    assert doubled() == 10


def test_is_accessor(wyb):
    count, _ = create_signal(0)
    assert is_accessor(count)
    assert is_accessor(create_memo(lambda: 1))
    assert not is_accessor(0)
    assert not is_accessor("x")
    assert not is_accessor(lambda x: x)


# ---------------------------------------------------------------------------
# Memos
# ---------------------------------------------------------------------------


def test_memo_is_eager_and_cached(wyb):
    count, set_count = create_signal(1)
    runs: list[int] = []
    doubled = create_memo(lambda: (runs.append(1), count() * 2)[1])
    assert isinstance(doubled, Memo)
    assert runs == [1]
    assert doubled() == 2
    assert doubled() == 2
    assert runs == [1]
    set_count(2)
    flush()
    assert runs == [1]
    assert doubled() == 4
    assert runs == [1, 1]


def test_memo_receives_previous_value(wyb):
    count, set_count = create_signal(1)
    total = create_memo(lambda prev: (prev or 0) + count())
    assert total() == 1
    set_count(5)
    flush()
    assert total() == 6


def test_memo_diamond_is_glitch_free(wyb):
    a, set_a = create_signal(1)
    b = create_memo(lambda: a() + 1)
    c = create_memo(lambda: a() * 10)
    seen: list[tuple[int, int]] = []
    d = create_memo(lambda: (seen.append((b(), c())), b() + c())[1])
    assert d() == 12
    set_a(2)
    flush()
    assert d() == 23
    assert seen == [(2, 10), (3, 20)]


def test_memo_equal_result_does_not_propagate(wyb):
    count, set_count = create_signal(1)
    parity = create_memo(lambda: count() % 2)
    runs: list[int] = []
    label = create_memo(lambda: (runs.append(1), "odd" if parity() else "even")[1])
    assert label() == "odd"
    set_count(3)
    flush()
    assert label() == "odd"
    assert runs == [1]


def test_memo_unobserved_and_lazy(wyb):
    count, set_count = create_signal(1)
    events: list[str] = []
    m = create_memo(lambda: count() * 2, lazy=True, unobserved=lambda: events.append("unobserved"))
    eff = create_effect(m, lambda v: events.append(f"v{v}"))
    flush()
    assert events == ["v2"]
    eff.dispose()
    # The check is deferred to the end of the next flush so an effect that
    # drops and re-adds an edge during a recompute doesn't fire it.
    assert events == ["v2"]
    flush()
    assert events == ["v2", "unobserved"]
    assert not m._disposed
    set_count(3)
    flush()
    assert m() == 6


def test_memo_write_in_scope_raises_in_dev_mode(wyb):
    _, set_other = create_signal(0)
    bad = create_memo(lambda: set_other(1))
    with pytest.raises(WriteInScopeError):
        bad()


def test_write_in_scope_allowed_when_dev_mode_off(wyb):
    _warnings.set_dev_mode(False)
    try:
        other, set_other = create_signal(0)
        m = create_memo(lambda: set_other(1))
        assert m() == 1
        flush()
        assert other() == 1
    finally:
        _warnings.set_dev_mode(True)


# ---------------------------------------------------------------------------
# Effects
# ---------------------------------------------------------------------------


def test_effect_first_run_is_deferred_to_flush(wyb):
    count, set_count = create_signal(0)
    seen: list[int] = []
    create_effect(count, lambda v: seen.append(v))
    assert seen == []
    flush()
    assert seen == [0]
    set_count(1)
    flush()
    assert seen == [0, 1]


def test_effect_split_form_apply_receives_prev_and_is_untracked(wyb):
    count, set_count = create_signal(0)
    other, set_other = create_signal("a")
    seen: list[tuple[int, int | None]] = []

    def apply(value: int, prev: int | None) -> None:
        other()  # incidental read: must not subscribe
        seen.append((value, prev))

    create_effect(count, apply)
    flush()
    set_other("b")
    flush()
    assert seen == [(0, None)]
    set_count(1)
    flush()
    assert seen == [(0, None), (1, 0)]


def test_effect_apply_may_write_signals(wyb):
    count, set_count = create_signal(1)
    doubled, set_doubled = create_signal(0)
    create_effect(count, lambda v: set_doubled(v * 2))
    flush()
    assert doubled() == 2
    set_count(4)
    flush()
    assert doubled() == 8


def test_effect_single_form_write_raises(wyb):
    _, set_other = create_signal(0)
    errors: list[BaseException] = []
    create_tracked_effect(lambda: set_other(1), error=errors.append)
    flush()
    assert len(errors) == 1
    assert isinstance(errors[0], WriteInScopeError)


def test_effect_apply_cleanup_runs_before_next_apply_and_on_dispose(wyb):
    count, set_count = create_signal(0)
    log: list[str] = []

    def apply(v: int) -> object:
        log.append(f"apply{v}")
        return lambda: log.append(f"clean{v}")

    eff = create_effect(count, apply)
    flush()
    set_count(1)
    flush()
    assert log == ["apply0", "apply1"] or log == ["apply0", "clean0", "apply1"]
    assert "clean0" in log
    eff.dispose()
    assert log[-1] == "clean1"


def test_effect_defer_skips_first_apply(wyb):
    count, set_count = create_signal(0)
    seen: list[int] = []
    create_effect(count, lambda v: seen.append(v), defer=True)
    flush()
    assert seen == []
    set_count(1)
    flush()
    assert seen == [1]


def test_effect_compute_receives_previous_value(wyb):
    count, set_count = create_signal(1)
    seen: list[int] = []
    create_effect(lambda prev: (prev or 0) + count(), lambda v: seen.append(v))
    flush()
    set_count(2)
    flush()
    assert seen == [1, 3]


def test_effect_on_cleanup_runs_before_rerun_and_on_dispose(wyb):
    count, set_count = create_signal(0)
    log: list[str] = []

    def body() -> None:
        v = count()
        on_cleanup(lambda: log.append(f"clean{v}"))
        log.append(f"run{v}")

    eff = create_tracked_effect(body)
    flush()
    set_count(1)
    flush()
    assert log == ["run0", "clean0", "run1"]
    eff.dispose()
    assert log[-1] == "clean1"


def test_effect_error_handler(wyb):
    count, set_count = create_signal(0)
    errors: list[str] = []

    def body() -> None:
        if count() > 0:
            raise ValueError("boom")

    create_tracked_effect(body, error=lambda e: errors.append(str(e)))
    flush()
    set_count(1)
    flush()
    assert errors == ["boom"]


def test_effect_batches_multiple_writes_into_one_run(wyb):
    a, set_a = create_signal(1)
    b, set_b = create_signal(1)
    runs: list[int] = []
    create_effect(lambda: a() + b(), lambda v: runs.append(v))
    flush()
    set_a(2)
    set_b(2)
    flush()
    assert runs == [2, 4]


def test_effect_dispose_stops_updates(wyb):
    count, set_count = create_signal(0)
    seen: list[int] = []
    eff = create_effect(count, lambda v: seen.append(v))
    flush()
    eff.dispose()
    set_count(1)
    flush()
    assert seen == [0]


def test_render_effect_runs_immediately(wyb):
    count, set_count = create_signal(0)
    seen: list[int] = []
    create_render_effect(count, lambda v: seen.append(v))
    assert seen == [0]
    set_count(1)
    flush()
    assert seen == [0, 1]


def test_untrack_prevents_subscription(wyb):
    a, set_a = create_signal(1)
    b, set_b = create_signal(1)
    seen: list[int] = []
    create_effect(lambda: a() + untrack(b), lambda v: seen.append(v))
    flush()
    set_b(10)
    flush()
    assert seen == [2]
    set_a(2)
    flush()
    assert seen == [2, 12]


# ---------------------------------------------------------------------------
# Ownership
# ---------------------------------------------------------------------------


def test_create_root_disposes_children(wyb):
    count, set_count = create_signal(0)
    seen: list[int] = []
    disposers: list = []

    def body(dispose):
        disposers.append(dispose)
        create_effect(count, lambda v: seen.append(v))
        on_cleanup(lambda: seen.append(-1))
        return "result"

    assert create_root(body) == "result"
    flush()
    disposers[0]()
    set_count(1)
    flush()
    assert seen == [0, -1]


def test_get_owner_and_run_with_owner(wyb):
    captured: list = []
    create_root(lambda d: captured.append(get_owner()))
    owner = captured[0]
    assert owner is not None
    log: list[str] = []
    run_with_owner(owner, lambda: on_cleanup(lambda: log.append("cleaned")))
    owner.dispose()
    assert log == ["cleaned"]


def test_on_cleanup_outside_scope_raises(wyb):
    with pytest.raises(RuntimeError):
        on_cleanup(lambda: None)


def test_nested_effect_is_disposed_with_parent(wyb):
    outer, set_outer = create_signal(0)
    inner, set_inner = create_signal(0)
    seen: list[str] = []

    def body() -> None:
        outer()
        create_effect(inner, lambda v: seen.append(f"inner{v}"))

    create_tracked_effect(body)
    flush()
    flush()
    assert seen == ["inner0"]
    set_outer(1)
    flush()
    flush()
    set_inner(1)
    flush()
    # Only the surviving inner effect (from the second outer run) fires.
    assert seen.count("inner1") == 1
