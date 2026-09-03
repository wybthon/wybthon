"""Development-mode warnings and error reporting.

A process-wide `DEV_MODE` flag and helpers that surface clear,
actionable messages during development while keeping production builds
quiet. All output goes to `sys.stderr`.

Dev-mode diagnostics raised elsewhere in the framework:

- **Top-level reactive read**: a signal, memo, or prop was called at the
  top level of a component body, where the read isn't tracked.
- **Write in tracking scope**: a signal was written inside a memo, a
  single-function effect, or a reactive hole
  ([`WriteInScopeError`][wybthon.WriteInScopeError]).
- **Static list in `For`**: `For` received a plain list instead of an
  accessor, so it will only render once.
"""

from __future__ import annotations

import sys
import traceback
from typing import Any

__all__ = [
    "DEV_MODE",
    "set_dev_mode",
    "is_dev_mode",
    "warn",
    "warn_once",
    "log_error",
    "component_name",
    "warn_each_plain_list",
]

DEV_MODE: bool = True
"""Process-wide flag toggling Wybthon's development diagnostics.

Defaults to `True`. Production builds should call
[`set_dev_mode(False)`][wybthon.set_dev_mode] at startup.
"""


def set_dev_mode(enabled: bool) -> None:
    """Enable or disable development mode diagnostics globally.

    Args:
        enabled: When `False`, `warn` and `warn_once` become no-ops,
            `WriteInScopeError` is not raised, and tracebacks are
            suppressed in `log_error`.
    """
    global DEV_MODE
    DEV_MODE = enabled


def is_dev_mode() -> bool:
    """Return whether development mode is currently active."""
    return DEV_MODE


_seen_warnings: set[tuple[str, Any]] = set()


def _reset_warning_dedupe() -> None:
    """Test helper that clears the once-only warning cache."""
    _seen_warnings.clear()


def warn(message: str) -> None:
    """Print a development-mode warning to `stderr` (no-op when dev mode is off)."""
    if DEV_MODE:
        print(f"[wybthon] Warning: {message}", file=sys.stderr)


def warn_once(category: str, key: Any, message: str) -> None:
    """Print `message` at most once per `(category, key)` pair."""
    if not DEV_MODE:
        return
    cache_key = (category, key)
    if cache_key in _seen_warnings:
        return
    _seen_warnings.add(cache_key)
    warn(message)


def log_error(message: str, error: BaseException | None = None) -> None:
    """Log an error to `stderr`, with a traceback in dev mode.

    Always logs regardless of `DEV_MODE`, since errors indicate real
    problems.
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
        return str(name)
    cls = getattr(comp, "__class__", None)
    if cls:
        return str(cls.__name__)
    return repr(comp)


def warn_each_plain_list(component: Any) -> None:
    """Warn that [`For`][wybthon.For] received a static list."""
    name = component_name(component)
    warn_once(
        "each_plain_list",
        id(component),
        f"{name} received a plain list for `each=`. Pass an accessor "
        f"(e.g. `each=items` where `items, set_items = create_signal([])`) "
        f"so the list reacts to updates. A static list only renders once.",
    )
