"""Compile templates in test modules under pytest (registered as a `pytest11` plugin).

pytest imports test modules and `conftest.py` files through its own
loader, which rewrites `assert` statements, so Wybthon's import hook
never sees them. This plugin adds Wybthon's compiler to pytest's
rewriting step: a test module's components and `html(t"...")` calls
are compiled exactly as an application module's are. Its cached bytecode gets a tag
of its own, so a test module cached without the compiler is never reused.

The plugin is a top-level module, not part of the `wybthon` package, so
loading it doesn't import Wybthon before a coverage plugin starts
measuring. Installing Wybthon enables it; disable it with `-p no:wybthon`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

# Matches `wybthon._hook.COMPILER_TAG` (a test checks they agree).
COMPILER_TAG = "wyb4"

# Installed from a wheel, pytest marks every package in the plugin's
# distribution for assertion rewriting, Wybthon's own included. Its modules
# never need the compiler, and compiling them while they import would be
# circular.
_PACKAGE = Path(__file__).resolve().parent / "wybthon"


def _is_wybthon_module(module_path: Any) -> bool:
    return module_path is not None and Path(str(module_path)).resolve().is_relative_to(_PACKAGE)


# Matches `wybthon._hook.is_candidate` (a test checks they agree); copied so
# loading the plugin doesn't import Wybthon.
_NAMES = (b"component", b"Show", b"Match", b"Switch", b"Loading", b"Errored", b"client_only")


def _is_candidate(source: bytes) -> bool:
    if b"wybthon" not in source:
        return False
    if b"html" in source and (b't"' in source or b"t'" in source):
        return True
    return any(name in source for name in _NAMES)


def _install() -> None:
    try:
        from _pytest.assertion import rewrite
    except ImportError:  # pragma: no cover - pytest's internals moved
        return
    if getattr(rewrite.rewrite_asserts, "_wybthon", False):
        return
    original = rewrite.rewrite_asserts

    def rewrite_asserts(mod: Any, source: bytes, module_path: Any = None, config: Any = None) -> None:
        if _is_candidate(source) and not _is_wybthon_module(module_path):
            from wybthon.compiler import transform

            transform(mod, str(module_path or "<test>"), source.decode("utf-8", "replace"))
        original(mod, source, module_path, config)

    rewrite_asserts._wybthon = True  # type: ignore[attr-defined]
    rewrite.rewrite_asserts = rewrite_asserts
    rewrite.PYC_TAIL = f".{rewrite.PYTEST_TAG}-{COMPILER_TAG}{rewrite.PYC_EXT}"


_install()


def pytest_runtest_teardown(item: Any) -> None:
    """Unmount views a test rendered with `wybthon.testing.render` and left mounted.

    An error those views logged that no boundary handled, and that nothing
    raised yet, fails the test here. Only when the test imported
    `wybthon.testing`, so a test run that never renders never imports
    Wybthon here.
    """
    import sys

    testing = sys.modules.get("wybthon.testing")
    if testing is not None:
        testing.cleanup(check=True)
