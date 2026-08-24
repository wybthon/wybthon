"""Low-level reactivity tests: signal/effect/computed plus the new scheduler.

Signal writes apply immediately, but effects run on the next flush;
these tests call ``flush()`` explicitly (the browser does it on a
microtask automatically).
"""

from wybthon.reactivity import computed, effect, flush, signal


def test_signal_and_effect():
    s = signal(0)
    seen = []

    def watcher():
        seen.append(s.get())

    eff = effect(watcher)
    # Initial run
    assert seen == [0]
    s.set(1)
    flush()
    assert seen[-1] == 1
    eff.dispose()


def test_computed_updates():
    a = signal(2)
    b = computed(lambda: a.get() * 5)
    assert b.get() == 10
    a.set(3)
    # Memos are pull-based: no flush needed for reads.
    assert b.get() == 15


def test_writes_coalesce_automatically():
    """Multiple writes before a flush run dependent effects once."""
    a = signal(0)
    seen = []

    def watcher():
        seen.append(a.get())

    effect(watcher)
    assert seen == [0]
    a.set(1)
    a.set(2)
    a.set(3)
    flush()
    # Only the final value is observed; intermediate writes coalesced.
    assert seen == [0, 3]


def test_effect_dispose_cancels_pending():
    s = signal(0)
    seen = []

    def watcher():
        seen.append(s.get())

    eff = effect(watcher)
    assert seen == [0]
    # Disposal before the flush cancels the pending run.
    s.set(1)
    eff.dispose()
    flush()
    assert seen == [0]


def test_flush_deterministic_order():
    s = signal(0)
    seen = []

    def mk(name):
        def fn():
            seen.append((name, s.get()))

        return fn

    effect(mk("A"))
    effect(mk("B"))
    # Initial runs should be in subscription order
    assert seen[:2] == [("A", 0), ("B", 0)]
    s.set(1)
    flush()
    # Next runs should preserve FIFO order
    assert seen[-2:] == [("A", 1), ("B", 1)]


def test_flush_is_idempotent():
    s = signal(0)
    seen = []
    effect(lambda: seen.append(s.get()))
    s.set(1)
    flush()
    flush()
    assert seen == [0, 1]
