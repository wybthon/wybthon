import time

from wybthon import batch, computed, effect, signal


def test_signal_and_effect():
    s = signal(0)
    seen = []

    def watcher():
        seen.append(s.get())

    eff = effect(watcher)
    # Initial run
    assert seen == [0]
    s.set(1)
    # Allow async scheduler to run
    time.sleep(0.05)
    assert seen[-1] == 1
    eff.dispose()


def test_computed_updates():
    a = signal(2)
    b = computed(lambda: a.get() * 5)
    assert b.get() == 10
    a.set(3)
    time.sleep(0.05)
    assert b.get() == 15


def test_batch_coalesces():
    a = signal(0)
    seen = []

    def watcher():
        seen.append(a.get())

    effect(watcher)
    assert seen == [0]
    with batch():
        a.set(1)
        a.set(2)
        a.set(3)
    time.sleep(0.05)
    # Only the final value should be observed after batch
    assert seen[-1] == 3
