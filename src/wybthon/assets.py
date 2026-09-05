"""Explicit lazy application chunks produced by ``wyb build``."""

from __future__ import annotations

import importlib


async def load_chunk(name: str) -> None:
    """Fetch and mount a named production chunk, sharing concurrent requests."""
    try:
        from js import __WYB
    except ImportError as exc:
        raise RuntimeError("load_chunk requires a generated production bootstrap") from exc
    await __WYB.loadChunk(name)
    importlib.invalidate_caches()
