import asyncio
import time

from wybthon import batch, computed, effect, signal, use_resource


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


def test_effect_dispose_cancels_pending():
    s = signal(0)
    seen = []

    def watcher():
        seen.append(s.get())

    eff = effect(watcher)
    assert seen == [0]
    # Ensure disposal cancels any pending runs
    with batch():
        s.set(1)
        eff.dispose()
    time.sleep(0.05)
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
    time.sleep(0.05)
    # Next runs should preserve FIFO order
    assert seen[-2:] == [("A", 1), ("B", 1)]


def test_resource_cancel_sets_loading_false():
    # Define a fetcher that awaits a bit
    async def fetcher(signal=None):
        await asyncio.sleep(0.01)
        return 42

    res = use_resource(fetcher)
    # Immediately cancel; loading should become False soon after
    res.cancel()
    time.sleep(0.05)
    assert res.loading.get() is False
