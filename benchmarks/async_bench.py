"""Measure async publication separately from synchronous rendering benchmarks.

Run ``python benchmarks/async_bench.py --widths 10 100 1000``. No network,
DOM, or timers are involved: gated coroutines model independent requests.
Counts and publication assertions are deterministic; durations are descriptive.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import platform

from wybthon import create_effect, create_memo, create_root, create_signal, flush
from wybthon.diagnostics import inspect_transitions, profile, runtime_stats


async def tick():
    for _ in range(3):
        flush()
        await asyncio.sleep(0)
    flush()


async def measure(width):
    visible = [0] * width
    writes, gates = [], []
    dispose = None

    def setup(cleanup):
        nonlocal dispose
        dispose = cleanup
        for index in range(width):
            signal, write = create_signal(0)
            gate = asyncio.Event()
            writes.append(write)
            gates.append(gate)

            async def fetch(signal=signal, gate=gate):
                value = signal()
                if value:
                    await gate.wait()
                return value

            memo = create_memo(fetch)

            def apply(value, *, index=index):
                visible[index] = value

            create_effect(memo, apply)

    create_root(setup)
    await tick()
    with profile() as start:
        for write in writes:
            write(1)
        await tick()
    assert visible == [0] * width
    assert len(inspect_transitions()) == width
    with profile() as first:
        gates[-1].set()
        await tick()
    assert visible == [0] * (width - 1) + [1]
    assert len(inspect_transitions()) == width - 1
    with profile() as rest:
        for gate in gates[:-1]:
            gate.set()
        await tick()
    assert visible == [1] * width
    assert not inspect_transitions()
    dispose()
    await tick()
    stats = runtime_stats()
    assert stats["held_nodes"] == stats["held_applies"] == stats["tasks"] == 0
    return {
        "width": width,
        "start": start.as_dict(),
        "first_publish": first.as_dict(),
        "remaining_publish": rest.as_dict(),
    }


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--widths", type=int, nargs="+", default=[10, 100, 1000])
    args = parser.parse_args()
    if min(args.widths) < 1:
        parser.error("widths must be positive")
    results = [await measure(width) for width in args.widths]
    print(
        json.dumps(
            {"python": platform.python_version(), "platform": platform.platform(), "scenarios": results}, indent=2
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
