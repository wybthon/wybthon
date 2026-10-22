"""Compile templates in test modules under pytest (registered as a `pytest11` plugin).

pytest imports test modules and `conftest.py` files through its own
loader, which rewrites `assert` statements, so Wybthon's import hook
never sees them. This plugin adds Wybthon's compiler to pytest's
rewriting step: a test module's `html(t"...")` calls are compiled
exactly as an application module's are. Its cached bytecode gets a tag
of its own, so a test module cached without the compiler is never reused.

The plugin is a top-level module, not part of the `wybthon` package, so
loading it doesn't import Wybthon before a coverage plugin starts
measuring. Installing Wybthon enables it; disable it with `-p no:wybthon`.
"""

from __future__ import annotations

from typing import Any

# Matches `wybthon._hook.COMPILER_TAG` (a test checks they agree).
COMPILER_TAG = "wyb1"


def _is_candidate(source: bytes) -> bool:
    return b"wybthon" in source and b"html" in source and (b't"' in source or b"t'" in source)


def _install() -> None:
    try:
        from _pytest.assertion import rewrite
    except ImportError:  # pragma: no cover - pytest's internals moved
        return
    if getattr(rewrite.rewrite_asserts, "_wybthon", False):
        return
    original = rewrite.rewrite_asserts

    def rewrite_asserts(mod: Any, source: bytes, module_path: Any = None, config: Any = None) -> None:
        if _is_candidate(source):
            from wybthon.compiler import transform

            transform(mod, str(module_path or "<test>"), source.decode("utf-8", "replace"))
        original(mod, source, module_path, config)

    rewrite_asserts._wybthon = True  # type: ignore[attr-defined]
    rewrite.rewrite_asserts = rewrite_asserts
    rewrite.PYC_TAIL = f".{rewrite.PYTEST_TAG}-{COMPILER_TAG}{rewrite.PYC_EXT}"


_install()
