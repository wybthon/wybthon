"""Small testing helpers that exercise the real scheduler and renderer.

Use an installed Python backend for native tests or the browser backend for
Pyodide tests. The helpers never replace reactive primitives with mocks.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

from . import kernel
from .dom import Element
from .reactivity import _core
from .reconciler import Root, render


@contextmanager
def reactive_scope() -> Iterator[_core.Owner]:
    """Own test computations and dispose them deterministically at scope exit."""
    owner = _core.Owner()
    previous = _core._current_owner
    _core._current_owner = owner
    try:
        yield owner
    finally:
        _core._current_owner = previous
        owner.dispose()
        _core.flush()


@contextmanager
def render_test(view: Any, container: Element | str | None = None) -> Iterator[Root]:
    """Render a fixture and release its tree, listeners, and temporary container."""
    owned = container is None
    target = Element("div") if owned else container
    assert target is not None
    root = render(view, target)
    try:
        yield root
    finally:
        root.dispose()
        if owned:
            kernel.emit((kernel.OP_RELEASE, [root.node_id]))
            kernel.commit()


async def tick(rounds: int = 2) -> None:
    """Drain ready asyncio continuations and flush reactive work."""
    if rounds < 1:
        raise ValueError("rounds must be positive")
    for _ in range(rounds):
        await asyncio.sleep(0)
        _core.flush()


async def wait_for(predicate: Callable[[], bool], *, timeout: float = 1, interval: float = 0.001) -> None:
    """Wait for an observable condition, raising TimeoutError on failure."""
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(interval)
            _core.flush()
