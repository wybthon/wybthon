"""Load the rest of the standard library when a trimmed build needs it (RFC 0008).

`wyb build` ships a standard library trimmed to the modules an app
imports (see `wybthon._stdlib`). If the app imports one it left out
(by name at run time, say), this finder fetches the rest of the library
synchronously, mounts it, and lets the import continue. It only ever
fetches once, and only for standard library modules.
"""

from __future__ import annotations

import importlib
import importlib.machinery
import sys
from typing import Any

__all__ = ["install"]

_MOUNT = "/lib/python-rest.zip"
_url: str | None = None
_loaded = False
_names: frozenset[str] = frozenset()
_packages: tuple[str, ...] = ()


def _in_rest(fullname: str) -> bool:
    if fullname in _names or fullname.partition(".")[0] in _names:
        return True
    return any(fullname.startswith(package) for package in _packages)


class _RestFinder:
    """The last finder on `sys.meta_path`: it only sees imports nothing else found."""

    @classmethod
    def find_spec(cls, fullname: str, path: Any = None, target: Any = None) -> Any:
        if _loaded or _url is None or not _in_rest(fullname):
            return None
        _load()
        return importlib.machinery.PathFinder.find_spec(fullname, path, target)

    @classmethod
    def invalidate_caches(cls) -> None:
        pass


def _load() -> None:
    global _loaded
    _loaded = True
    import zipfile

    import pyodide_js
    from js import __wybFetchSync

    pyodide_js.FS.writeFile(_MOUNT, __wybFetchSync(_url))
    sys.path.append(_MOUNT)
    with zipfile.ZipFile(_MOUNT) as archive:
        folders = {name.rpartition("/")[0] for name in archive.namelist() if "/" in name}
    # Packages already imported from the trimmed library find their other
    # submodules in the rest too.
    for name, module in list(sys.modules.items()):
        package_path = getattr(module, "__path__", None)
        if package_path is None or name.partition(".")[0] not in sys.stdlib_module_names:
            continue
        folder = name.replace(".", "/")
        if folder in folders:
            entry = f"{_MOUNT}/{folder}"
            if entry not in package_path:
                package_path.append(entry)
    importlib.invalidate_caches()
    print("[wybthon] loaded the rest of the standard library for an import the build didn't see", file=sys.stderr)


def install(url: str, index: str) -> None:
    """Fetch the rest of the standard library from `url` if an import of a module in `index` needs it.

    `index` lists the rest's modules: whole top-level names, and
    `package.*` for a package whose other submodules are there.
    """
    global _url, _names, _packages
    _url = url
    entries = index.split()
    _names = frozenset(entry for entry in entries if not entry.endswith(".*"))
    _packages = tuple(entry[:-1] for entry in entries if entry.endswith(".*"))
    if _RestFinder not in sys.meta_path:
        sys.meta_path.append(_RestFinder)
