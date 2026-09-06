"""Cooperative CPU work that gives the browser opportunities to paint."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable, Iterable
from time import perf_counter
from typing import Any


async def yield_to_browser() -> None:
    """Yield through a timer task, allowing input and rendering between chunks."""
    await asyncio.sleep(0.001)


async def map_cooperative[T, U](values: Iterable[T], fn: Callable[[T], U], *, budget_ms: float = 8) -> list[U]:
    """Map CPU work in bounded time slices; cancellation interrupts between slices.

    A single callback must itself be short. The budget limits time between
    callbacks, and can't preempt a long Python function.
    """
    if budget_ms <= 0:
        raise ValueError("budget_ms must be positive")
    result = []
    deadline = perf_counter() + budget_ms / 1000
    for item in values:
        value: Any = fn(item)
        result.append(await value if inspect.isawaitable(value) else value)
        if perf_counter() >= deadline:
            await yield_to_browser()
            deadline = perf_counter() + budget_ms / 1000
    return result
