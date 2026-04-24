"""Development mode warnings and error reporting for Wybthon.

Provides a lightweight `DEV_MODE` flag and helper functions that
surface clear, actionable error messages during development while
keeping production builds quiet. All output goes to `sys.stderr` so
it never mixes with regular program output.

Built-in dev warnings include:

- `warn_destructured_prop`:
  a reactive prop accessor was unwrapped at component-setup time
  (loses reactivity).
- `warn_each_plain_list`:
  `For` / `Index` received a plain list rather than a getter (the
  list will only render once).
"""

from __future__ import annotations

import sys
import traceback
from typing import Any, Optional, Set, Tuple

__all__ = [
    "DEV_MODE",
    "set_dev_mode",
    "is_dev_mode",
    "warn",
    "warn_once",
    "log_error",
    "component_name",
    "warn_destructured_prop",
    "warn_each_plain_list",
]

DEV_MODE: bool = True
"""Process-wide flag toggling Wybthon's development warnings.

Defaults to `True`. Production builds should call
[`set_dev_mode(False)`][wybthon._warnings.set_dev_mode] at startup.
"""


def set_dev_mode(enabled: bool) -> None:
    """Enable or disable development mode warnings globally.

    Args:
        enabled: When `False`, `warn` and `warn_once` become no-ops
            and tracebacks are suppressed in `log_error`.
    """
    global DEV_MODE
    DEV_MODE = enabled


def is_dev_mode() -> bool:
    """Return whether development mode is currently active."""
    return DEV_MODE


_seen_warnings: Set[Tuple[str, Any]] = set()


def _reset_warning_dedupe() -> None:
    """Test helper that clears the once-only warning cache."""
    _seen_warnings.clear()


def warn(message: str) -> None:
    """Print a development-mode warning to `stderr`.

    Args:
        message: Warning text. Prefixed with `"[wybthon] Warning:"`.

    No-op when [`DEV_MODE`][wybthon._warnings.DEV_MODE] is `False`.
    """
    if DEV_MODE:
        print(f"[wybthon] Warning: {message}", file=sys.stderr)


def warn_once(category: str, key: Any, message: str) -> None:
    """Print `message` at most once for the given `(category, key)` pair.

    Args:
        category: Warning bucket (e.g., `"each_plain_list"`).
        key: Hashable identifier within the category. The same
            warning for the same key is only ever emitted once per
            process.
        message: Warning text.
    """
    if not DEV_MODE:
        return
    cache_key = (category, key)
    if cache_key in _seen_warnings:
        return
    _seen_warnings.add(cache_key)
    warn(message)


def log_error(message: str, error: Optional[Exception] = None) -> None:
    """Log an error to `stderr`, with an optional traceback in dev mode.

    Always logs regardless of `DEV_MODE` since errors indicate real
    problems. In dev mode the full traceback is included.

    Args:
        message: Short human-readable error message.
        error: Optional exception whose traceback should be printed.
    """
    print(f"[wybthon] Error: {message}", file=sys.stderr)
    if error is not None and DEV_MODE:
        traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)


def component_name(comp: Any) -> str:
    """Return a human-readable display name for a component or tag.

    Args:
        comp: A tag string, a function/class component, or any value.

    Returns:
        A display name suitable for embedding in dev warnings.
    """
    if isinstance(comp, str):
        return f"<{comp}>"
    name = getattr(comp, "__name__", None) or getattr(comp, "__qualname__", None)
    if name:
        return name
    cls = getattr(comp, "__class__", None)
    if cls:
        return cls.__name__
    return repr(comp)


def warn_destructured_prop(component: Any, prop_name: str) -> None:
    """Warn that a reactive prop accessor was unwrapped at component setup.

    Calling `my_prop()` in the component body **before** returning the
    VNode tree captures the *current* value into the closure, so
    subsequent parent updates will not propagate. Use the bare
    accessor inside the tree (`span(my_prop)`) or wrap the dependent
    expression in [`dynamic`][wybthon.dynamic]
    (`span(dynamic(lambda: f"v={my_prop()}"))`) to keep it reactive.

    Args:
        component: The component that read the prop.
        prop_name: Name of the prop that was unwrapped.
    """
    name = component_name(component)
    warn_once(
        "destructured_prop",
        (id(component), prop_name),
        f"Component {name} unwrapped prop '{prop_name}' during setup. "
        f"This freezes the value -- subsequent parent updates won't propagate. "
        f"Pass the accessor itself ({prop_name}) into the VNode tree, "
        f"or wrap the expression in `dynamic(lambda: ...)` to keep it reactive.",
    )


def warn_each_plain_list(component: Any) -> None:
    """Warn that [`For`][wybthon.For] / [`Index`][wybthon.Index] received a static list.

    Args:
        component: The flow control component receiving the prop.
    """
    name = component_name(component)
    warn_once(
        "each_plain_list",
        id(component),
        f"{name} received a plain list for `each=`.  Pass a signal accessor "
        f"(e.g. `each=items` where `items, set_items = create_signal([])`) "
        f"so the list reacts to updates.  A static list will only render once.",
    )
