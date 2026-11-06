"""What a boot snapshot holds (RFC 0006).

The production bootstrap builds a memory snapshot of a Pyodide runtime
in a worker, after the first visit, and restores it on later visits
instead of starting Python and importing the framework again. `preload`
runs in that worker before the snapshot is taken: everything it imports
is already imported when a restored page starts.

Only modules that don't touch the page are imported here. A snapshot
can't hold references to JavaScript objects, and the worker has no
document, so Wybthon imports `js` lazily everywhere; application modules,
which may read `window` when they're imported, aren't preloaded.
"""

from __future__ import annotations

import importlib

__all__ = ["MODULES", "preload"]

# Standard library modules applications commonly import, on top of the ones
# Wybthon imports itself.
_STDLIB = (
    "asyncio",
    "collections",
    "dataclasses",
    "datetime",
    "enum",
    "functools",
    "itertools",
    "json",
    "math",
    "random",
    "re",
    "typing",
)

# The framework's browser modules, including the ones `import wybthon` loads
# on first use.
MODULES = (
    "wybthon",
    "wybthon.compiler",
    "wybthon.context",
    "wybthon.dom",
    "wybthon.error_boundary",
    "wybthon.events",
    "wybthon.flow",
    "wybthon.forms",
    "wybthon.kernel",
    "wybthon.lazy",
    "wybthon.loading",
    "wybthon.portal",
    "wybthon.reconciler",
    "wybthon.router",
    "wybthon.store",
    "wybthon.templates",
    "wybthon._regions",
)


def preload() -> list[str]:
    """Import the snapshot's modules; returns the ones that failed to import."""
    failed = []
    for name in _STDLIB + MODULES:
        try:
            importlib.import_module(name)
        except Exception:
            failed.append(name)
    return failed
