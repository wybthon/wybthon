"""The import hook that compiles application modules as they're imported.

`import wybthon` installs it. It's deliberately small: it decides which
modules need the compiler and caches what the compiler produces, and it
only imports [`wybthon.compiler`][wybthon.compiler] (and `ast`) when a
module actually needs compiling.

- **Candidates.** A source file outside the standard library whose text
  mentions `wybthon` and `html` and contains a t-string. Everything else
  loads exactly as it would without the hook.
- **Built bytecode.** `wyb build` writes compiled, unchecked-hash bytecode
  into the archives. The hook uses it as is, so a production page never
  compiles anything.
- **Cache.** Compiled code is cached next to the normal bytecode under its
  own optimization tag (`module.cpython-314.opt-wyb2.pyc`), validated
  against the source's modification time and size. A plain compile cached
  before the hook was installed is never mistaken for a compiled one.
"""

from __future__ import annotations

import marshal
import os
import sys
from importlib.machinery import PathFinder, SourceFileLoader
from importlib.util import MAGIC_NUMBER, cache_from_source
from types import CodeType
from typing import Any

__all__ = ["install", "uninstall", "is_candidate", "COMPILER_TAG"]

# Bump when the compiler's output changes, so cached compiled code is rebuilt.
COMPILER_TAG = "wyb2"

_STDLIB = os.path.dirname(os.__file__) + os.sep
# Wybthon's own modules never use the compiler.
_PACKAGE = os.path.dirname(os.path.abspath(__file__)) + os.sep


def is_candidate(source: bytes) -> bool:
    """Whether a module's source may contain `html(t"...")` calls for the compiler."""
    return b"wybthon" in source and b"html" in source and (b't"' in source or b"t'" in source)


def _skipped(path: str) -> bool:
    if not path.endswith(".py") or path.startswith(_PACKAGE):
        return True
    return path.startswith(_STDLIB) and "-packages" + os.sep not in path


def _built(path: str) -> bool:
    """Whether the module's regular bytecode is an unchecked-hash file, as `wyb build` writes."""
    try:
        with open(cache_from_source(path), "rb") as handle:
            header = handle.read(8)
    except OSError, NotImplementedError, ValueError:
        return False
    return len(header) == 8 and header[:4] == MAGIC_NUMBER and int.from_bytes(header[4:8], "little") == 0b01


class _Loader(SourceFileLoader):
    """A source loader that runs candidate modules through the compiler."""

    def get_code(self, fullname: str) -> CodeType | None:
        path = self.get_filename(fullname)
        if _built(path):
            return super().get_code(fullname)
        source = self.get_data(path)
        if not is_candidate(source):
            return super().get_code(fullname)
        stats = self.path_stats(path)
        mtime = int(stats["mtime"]) & 0xFFFFFFFF
        size = int(stats.get("size", len(source))) & 0xFFFFFFFF
        try:
            cache = cache_from_source(path, optimization=COMPILER_TAG)
        except NotImplementedError, ValueError:
            cache = None
        if cache is not None:
            try:
                data = self.get_data(cache)
            except OSError:
                data = b""
            if (
                len(data) > 16
                and data[:4] == MAGIC_NUMBER
                and data[4:8] == b"\0\0\0\0"
                and int.from_bytes(data[8:12], "little") == mtime
                and int.from_bytes(data[12:16], "little") == size
            ):
                try:
                    code = marshal.loads(data[16:])
                except EOFError, ValueError, TypeError:
                    code = None
                if isinstance(code, CodeType):
                    return code
        from .compiler import compile_source

        code = compile_source(source, path)
        if cache is not None and not sys.dont_write_bytecode:
            payload = MAGIC_NUMBER + b"\0\0\0\0" + mtime.to_bytes(4, "little") + size.to_bytes(4, "little")
            try:
                self.set_data(cache, payload + marshal.dumps(code))
            except OSError, NotImplementedError:
                pass
        return code


class _Finder:
    """Finds modules with the regular path finder and compiles the candidates."""

    @classmethod
    def find_spec(cls, fullname: str, path: Any = None, target: Any = None) -> Any:
        spec = PathFinder.find_spec(fullname, path, target)
        if spec is None or type(spec.loader) is not SourceFileLoader or spec.origin is None:
            return spec
        if _skipped(spec.origin):
            return spec
        spec.loader = _Loader(spec.loader.name, spec.loader.path)
        return spec

    @classmethod
    def invalidate_caches(cls) -> None:
        PathFinder.invalidate_caches()


def install() -> None:
    """Compile templates in modules imported from now on (idempotent).

    `import wybthon` calls this. The hook goes right before the regular
    path finder, so finders installed earlier (pytest's assertion
    rewriting, for one) keep handling the modules they claim.
    """
    if _Finder in sys.meta_path:
        return
    for index, finder in enumerate(sys.meta_path):
        if finder is PathFinder:
            sys.meta_path.insert(index, _Finder)
            return
    sys.meta_path.append(_Finder)


def uninstall() -> None:
    """Remove the import hook."""
    while _Finder in sys.meta_path:
        sys.meta_path.remove(_Finder)
