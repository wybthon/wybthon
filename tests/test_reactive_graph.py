"""Reactive-graph guarantees: glitch-free, lazy, minimal recompute, auto-batched.

These tests pin down the SolidJS 2.0-style semantics of the reactive core:

- Writes apply to signal values immediately; **memo reads are always
  consistent** with the latest writes (pull-based).
- Effects run on the next `flush()` (automatic batching): several writes
  before a flush produce exactly one effect run.
- Updates are **glitch-free**: an effect reading several memos derived from a
  common source never observes an inconsistent, half-updated combination, and
  runs once per flush rather than once per intermediate edge.
- Memos are **lazy** (pull-based): they recompute only when read after a
  dependency changed, and not at all if never read.
- Memos **short-circuit** equal results: when a recomputed memo value is
  unchanged, its downstream consumers are not re-run.
"""

from wybthon.reactivity import create_effect, create_memo, create_signal, flush, untrack

# --------------------------------------------------------------------------- #
# Write/flush semantics
# --------------------------------------------------------------------------- #


def test_writes_apply_immediately_effects_run_on_flush():
    count, set_count = create_signal(0)
    seen = []
    create_effect(lambda: seen.append(count()))

    assert seen == [0]
    set_count(1)
    assert count() == 1, "the value applies immediately"
    assert seen == [0], "the effect waits for the flush"
    flush()
    assert seen == [0, 1]
    set_count(2)
    flush()
    assert seen == [0, 1, 2]


def test_memo_readable_synchronously_after_set():
    a, set_a = create_signal(2)
    doubled = create_memo(lambda: a() * 2)
    assert doubled() == 4
    set_a(5)
    # Memos are pull-based; no flush needed for reads.
    assert doubled() == 10


def test_no_run_when_value_unchanged_default_equality():
    count, set_count = create_signal(0)
    runs = []
    create_effect(lambda: runs.append(count()))
    assert runs == [0]
    set_count(0)  # equal -> no notification
    flush()
    assert runs == [0]
    set_count(1)
    flush()
    assert runs == [0, 1]


# --------------------------------------------------------------------------- #
# Glitch-free diamond
# --------------------------------------------------------------------------- #


def test_diamond_is_glitch_free():
    """A diamond (A -> B, A -> C, {B,C} -> effect) settles consistently, once."""
    a, set_a = create_signal(1)
    b = create_memo(lambda: a() + 1)
    c = create_memo(lambda: a() * 2)

    observed = []
    runs = [0]

    def eff():
        runs[0] += 1
        # Both reads must reflect the *same* value of ``a``.
        observed.append((b(), c()))

    create_effect(eff)
    assert observed == [(2, 2)]
    assert runs[0] == 1

    set_a(3)
    flush()
    # Effect ran exactly once more, and saw a fully-consistent (b, c).
    assert runs[0] == 2
    assert observed == [(2, 2), (4, 6)]

    set_a(10)
    flush()
    assert runs[0] == 3
    assert observed[-1] == (11, 20)


def test_deep_chain_settles_once():
    """A long memo chain delivers a single, final effect run."""
    src, set_src = create_signal(0)
    m1 = create_memo(lambda: src() + 1)
    m2 = create_memo(lambda: m1() + 1)
    m3 = create_memo(lambda: m2() + 1)
    m4 = create_memo(lambda: m3() + 1)

    seen = []
    create_effect(lambda: seen.append(m4()))
    assert seen == [4]

    set_src(10)
    flush()
    # One run, final value only -- no intermediate edges leaked through.
    assert seen == [4, 14]


# --------------------------------------------------------------------------- #
# Laziness (pull-based memos)
# --------------------------------------------------------------------------- #


def test_unread_memo_never_computes():
    a, set_a = create_signal(0)
    calls = [0]

    def compute():
        calls[0] += 1
        return a() * 2

    _ = create_memo(compute)
    # Never read -> never computed, even after the dependency changes.
    assert calls[0] == 0
    set_a(1)
    flush()
    assert calls[0] == 0


def test_memo_recomputes_lazily_only_on_read_after_change():
    a, set_a = create_signal(1)
    calls = [0]

    def compute():
        calls[0] += 1
        return a() * 10

    m = create_memo(compute)

    assert m() == 10
    assert calls[0] == 1

    # Reading again without a change does not recompute.
    assert m() == 10
    assert calls[0] == 1

    set_a(2)
    # The change alone does not recompute (lazy); the read triggers it.
    assert calls[0] == 1
    assert m() == 20
    assert calls[0] == 2


def test_memo_recomputes_once_for_multiple_changes_before_read():
    a, set_a = create_signal(1)
    calls = [0]
    m = create_memo(lambda: (calls.__setitem__(0, calls[0] + 1), a())[1])

    assert m() == 1
    assert calls[0] == 1

    set_a(2)
    set_a(3)
    set_a(4)
    # No reads in between -> coalesced into a single recompute on next read.
    assert calls[0] == 1
    assert m() == 4
    assert calls[0] == 2


# --------------------------------------------------------------------------- #
# Equality short-circuit (minimal recompute)
# --------------------------------------------------------------------------- #


def test_downstream_effect_skipped_when_memo_value_unchanged():
    """Changing the source but not the memo's value must not re-run consumers."""
    n, set_n = create_signal(1)
    is_positive = create_memo(lambda: n() > 0)

    runs = []
    create_effect(lambda: runs.append(is_positive()))
    assert runs == [True]

    # n changes 1 -> 2, but ``is_positive`` stays True: no downstream re-run.
    set_n(2)
    flush()
    assert runs == [True]

    set_n(5)
    flush()
    assert runs == [True]

    # Crossing zero flips the memo, which *does* re-run the consumer.
    set_n(-1)
    flush()
    assert runs == [True, False]


def test_memo_short_circuit_prevents_recompute_of_chained_memo():
    n, set_n = create_signal(1)
    parity = create_memo(lambda: n() % 2)
    downstream_calls = [0]

    def downstream():
        downstream_calls[0] += 1
        return f"parity={parity()}"

    d = create_memo(downstream)

    assert d() == "parity=1"
    assert downstream_calls[0] == 1

    # 1 -> 3: parity stays 1, so the downstream memo must not recompute.
    set_n(3)
    assert d() == "parity=1"
    assert downstream_calls[0] == 1

    # 3 -> 4: parity flips to 0, downstream recomputes.
    set_n(4)
    assert d() == "parity=0"
    assert downstream_calls[0] == 2


# --------------------------------------------------------------------------- #
# Automatic batching and untracking
# --------------------------------------------------------------------------- #


def test_writes_batch_automatically_across_sources():
    a, set_a = create_signal(0)
    b, set_b = create_signal(0)
    runs = [0]
    create_effect(lambda: (runs.__setitem__(0, runs[0] + 1), a(), b()))

    assert runs[0] == 1
    set_a(1)
    set_b(2)
    flush()
    # Two sources changed before the flush -> exactly one extra run.
    assert runs[0] == 2


def test_untrack_does_not_subscribe():
    a, set_a = create_signal(0)
    b, set_b = create_signal(100)
    seen = []

    create_effect(lambda: seen.append((a(), untrack(b))))
    assert seen == [(0, 100)]

    # Changing the untracked signal does not re-run the effect.
    set_b(200)
    flush()
    assert seen == [(0, 100)]

    # Changing the tracked signal does, and reads the latest untracked value.
    set_a(1)
    flush()
    assert seen == [(0, 100), (1, 200)]


def test_effect_writing_signal_settles_within_one_flush():
    """A user effect that writes a signal re-settles before flush() returns."""
    a, set_a = create_signal(0)
    b, set_b = create_signal(0)
    seen = []

    create_effect(lambda: set_b(a() * 10))
    create_effect(lambda: seen.append(b()))
    flush()
    assert seen[-1] == 0

    set_a(2)
    flush()
    assert seen[-1] == 20
