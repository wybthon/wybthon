"""Small helpers shared across E2E fixture feature pages.

``tid`` emits a stable ``data-testid`` attribute. Wybthon's HTML element
helpers pass arbitrary keyword props straight through (``class_`` and
``html_for`` are the only remapped names), and CPython permits spreading a
dict with non-identifier keys into ``**kwargs``. That lets every fixture use
``span("x", **tid("rx-value"))`` to attach a hyphenated test id without
reaching for the low-level ``h`` constructor.
"""

from typing import Any, Dict


def tid(name: str) -> Dict[str, str]:
    """Return a props fragment that renders ``data-testid="<name>"``."""
    return {"data-testid": name}


def feature_ids(names: Any) -> Dict[str, str]:
    """Build a quick lookup of nav test ids (kept for readability in tests)."""
    return {n: f"nav-{n}" for n in names}
