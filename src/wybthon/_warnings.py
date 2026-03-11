"""Development mode warnings and error reporting for Wybthon.

Provides a lightweight ``DEV_MODE`` flag and helper functions that surface
clear, actionable error messages during development while keeping production
builds quiet.  All output goes to ``sys.stderr`` so it never mixes with
regular program output.
"""

from __future__ import annotations

import sys
import traceback
from typing import Any, Optional

__all__ = ["DEV_MODE", "set_dev_mode", "is_dev_mode", "warn", "log_error", "component_name"]

DEV_MODE: bool = True


def set_dev_mode(enabled: bool) -> None:
    """Enable or disable development mode warnings globally."""
    global DEV_MODE
    DEV_MODE = enabled


def is_dev_mode() -> bool:
    """Return whether development mode is currently active."""
    return DEV_MODE


def warn(message: str) -> None:
    """Print a development-mode warning to stderr.

    No-op when ``DEV_MODE`` is ``False``.
    """
    if DEV_MODE:
        print(f"[wybthon] Warning: {message}", file=sys.stderr)


def log_error(message: str, error: Optional[Exception] = None) -> None:
    """Log an error with an optional traceback to stderr.

    Always logs regardless of ``DEV_MODE`` since errors indicate real
    problems.  In dev mode the full traceback is included.
    """
    print(f"[wybthon] Error: {message}", file=sys.stderr)
    if error is not None and DEV_MODE:
        traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)


def component_name(comp: Any) -> str:
    """Return a human-readable display name for a component or tag."""
    if isinstance(comp, str):
        return f"<{comp}>"
    name = getattr(comp, "__name__", None) or getattr(comp, "__qualname__", None)
    if name:
        return name
    cls = getattr(comp, "__class__", None)
    if cls:
        return cls.__name__
    return repr(comp)
