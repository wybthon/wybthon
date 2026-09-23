"""Opt-in runtime counters and JSON-ready ownership graph inspection.

Profiling is disabled by default. Capture counters around a specific operation
and compare work counts as well as elapsed time; these are application metrics,
not cross-framework benchmark rankings.
"""

from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any, Iterator

_active: Profile | None = None


@dataclass(slots=True)
class Profile:
    """Counters and elapsed seconds for a measured operation."""

    counts: Counter[str] = field(default_factory=Counter)
    elapsed: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        """Return a serializable report."""
        return {"elapsed_ms": self.elapsed * 1000, **self.counts}


def _count(name: str, amount: int = 1) -> None:
    active = _active
    if active is not None:
        active.counts[name] += amount


@contextmanager
def profile() -> Iterator[Profile]:
    """Capture work performed in this scope, including explicit flush calls."""
    global _active
    previous = _active
    result = _active = Profile()
    start = perf_counter()
    try:
        yield result
    finally:
        result.elapsed = perf_counter() - start
        _active = previous


def inspect_graph(owner: Any) -> dict[str, Any]:
    """Inspect ownership and dependencies without evaluating or retaining values."""
    from .reactivity import _core

    nodes = []
    edges = []
    queue = [owner]
    seen = set()
    while queue:
        node = queue.pop()
        if node is None or id(node) in seen:
            continue
        seen.add(id(node))
        entry = {"id": id(node), "type": type(node).__name__, "disposed": getattr(node, "_disposed", False)}
        if hasattr(node, "_label"):
            entry["name"] = node._label()
        held = _core._node_tx.get(node)
        if held is not None:
            entry["transition"] = held.root().id
        if isinstance(node, _core.Computation):
            entry["prepared_owner"] = id(node._prepared_owner) if node._prepared_owner is not None else None
            entry["committed_owner"] = id(node._committed_owner) if node._committed_owner is not None else None
            entry["blocked_by"] = sorted(
                {
                    _core._node_tx[source].root().id
                    for source, mode in (node._sources or {}).items()
                    if mode & _core._R_NORMAL and source in _core._node_tx
                }
            )
            entry["state"] = ("clean", "check", "dirty")[node._state]
            entry["pending"] = bool(node._async and node._async.pending)
            for source, mode in (node._sources or {}).items():
                edges.append(
                    {
                        "from": id(source),
                        "to": id(node),
                        "kind": "dependency",
                        "read": "+".join(
                            label for bit, label in ((1, "ordinary"), (2, "latest"), (4, "pending")) if mode & bit
                        ),
                    }
                )
                queue.append(source)
            if node._apply_owner is not None:
                edges.append({"from": id(node), "to": id(node._apply_owner), "kind": "owns"})
                queue.append(node._apply_owner)
        if isinstance(node, _core.Owner):
            entry["tasks"] = len(node._tasks or ())
            for child in (node._children or {}).values():
                edges.append({"from": id(node), "to": id(child), "kind": "owns"})
                queue.append(child)
        nodes.append(entry)
    return {"nodes": nodes, "edges": edges, "transitions": inspect_transitions()}


def inspect_transitions() -> list[dict[str, Any]]:
    """Explain pending publication without reading values or mutating the graph.

    IDs match ``inspect_graph``. A group is ready once its action count and
    pending computations are empty. Held applies identify consumers whose
    prepared results haven't reached the DOM or an effect yet.
    """
    from .reactivity import _core

    return [
        {
            "id": tx.id,
            "actions": tx.holds,
            "pending": [id(comp) for comp in tx.pending],
            "held": [id(node) for node in tx.snapshot],
            "applies": [id(comp) for comp in tx.held_applies],
            "affected": [id(node) for node in tx.affected],
        }
        for tx in _core._transitions
    ]


def runtime_stats() -> dict[str, Any]:
    """Return live scheduler and backend registry counts."""
    from . import kernel
    from .reactivity import _core

    return {
        "tasks": len(_core._tasks),
        "transitions": len(_core._transitions),
        "held_nodes": len(_core._held),
        "held_applies": sum(len(tx.held_applies) for tx in _core._transitions),
        "staged": len(_core._staged),
        "render_queue": len(_core._render_queue),
        "effect_queue": len(_core._effect_queue),
        **kernel.stats(),
    }
