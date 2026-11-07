"""Trim Pyodide's standard library to what an app imports (`wyb build`, RFC 0008).

Pyodide's `python_stdlib.zip` is 2.5 MB, and every first visit downloads
all of it, though an app imports a fraction. The build splits it in two:

- **The trimmed library**, which the page loads in place of Pyodide's
  (`loadPyodide({stdLibURL})`): every module Pyodide imports to boot,
  every module the framework and the application import, and everything
  those import in turn, found by reading their `import` statements.
- **The rest**, fetched only if a module outside the trimmed library is
  ever imported (an `import` inside a string, `importlib.import_module`,
  a codec looked up by name). `wybthon._stdlib_rest` finds such an
  import, fetches the rest synchronously, and lets the import continue,
  so trimming never breaks an app; it only makes that one import slower.

Set `stdlib = "full"` in `wybthon.toml` to ship Pyodide's library as is.
"""

from __future__ import annotations

import ast
import hashlib
import io
import sys
import urllib.request
import zipfile
from collections.abc import Iterable
from pathlib import Path

__all__ = ["trim", "fetch_stdlib", "BOOT_MODULES"]

# What Pyodide 314 imports to boot a Wybthon app, measured in Chromium, and
# the codecs a page commonly needs (the closure below adds what these import).
BOOT_MODULES = frozenset(
    """
    __future__ _collections_abc _colorize _opcode_metadata _py_warnings _pyodide _pyodide._base
    _pyodide._core_docs _pyodide._future_helper _pyodide._importhook _pyodide.docs_argspec _pyodide.docstring
    _pyodide.jsbind _sitebuiltins _ssl _weakrefset abc annotationlib ast asyncio asyncio.base_events
    asyncio.base_futures asyncio.base_subprocess asyncio.base_tasks asyncio.constants asyncio.coroutines
    asyncio.events asyncio.exceptions asyncio.format_helpers asyncio.futures asyncio.graph asyncio.locks
    asyncio.log asyncio.mixins asyncio.protocols asyncio.queues asyncio.runners asyncio.selector_events
    asyncio.sslproto asyncio.staggered asyncio.streams asyncio.subprocess asyncio.taskgroups asyncio.tasks
    asyncio.threads asyncio.timeouts asyncio.transports asyncio.trsock asyncio.unix_events base64 bisect bz2
    codecs codeop collections collections.abc compression compression._common compression._common._streams
    compression.zstd compression.zstd._zstdfile concurrent concurrent.futures concurrent.futures._base
    contextlib contextvars copy copyreg dataclasses datetime dis encodings encodings.aliases encodings.cp437
    encodings.utf_8 enum fnmatch functools genericpath glob hashlib heapq html html.entities http importlib
    importlib._abc importlib._bootstrap importlib._bootstrap_external importlib.abc importlib.machinery
    importlib.readers importlib.resources importlib.resources._adapters importlib.resources._common
    importlib.resources._functional importlib.resources._itertools importlib.resources.abc
    importlib.resources.readers importlib.util inspect io ipaddress json json.decoder json.encoder json.scanner
    keyword linecache locale logging lzma ntpath opcode operator os pathlib pathlib._os posixpath pyodide
    pyodide._package_loader pyodide._state pyodide.code pyodide.common pyodide.ffi pyodide.webloop random re
    re._casefix re._compiler re._constants re._parser reprlib selectors shutil signal site socket ssl stat
    string string.templatelib struct subprocess tempfile textwrap threading token tokenize traceback types
    typing urllib urllib.parse warnings weakref zipfile zipfile._path zipfile._path.glob zipimport
    encodings.ascii encodings.latin_1 encodings.utf_8_sig encodings.utf_16 encodings.utf_16_le
    encodings.utf_16_be encodings.utf_32 encodings.idna encodings.punycode encodings.raw_unicode_escape
    encodings.unicode_escape encodings.charmap encodings.cp1252
    """.split()
)

# Packages Pyodide imports from C while it boots, before the fallback for
# trimmed modules exists: kept whole.
WHOLE_PACKAGES = frozenset({"_pyodide", "pyodide"})


def _module_names(archive: zipfile.ZipFile) -> dict[str, str]:
    """Module name -> its file in the archive (a package's `__init__.py`)."""
    found: dict[str, str] = {}
    for name in archive.namelist():
        if not name.endswith(".py"):
            continue
        parts = name[:-3].split("/")
        if parts[-1] == "__init__":
            parts.pop()
        if parts:
            found[".".join(parts)] = name
    return found


def _module_level(tree: ast.Module) -> Iterable[ast.AST]:
    """The statements that run when a module is imported: not function bodies.

    An import inside a function runs only if the function does; when it
    does and its module was trimmed, the fallback fetches it.
    """
    pending: list[ast.AST] = list(tree.body)
    while pending:
        node = pending.pop()
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda):
            continue
        if isinstance(node, ast.If) and (_is_type_checking(node.test) or _is_main(node.test)):
            pending.extend(node.orelse)
            continue
        yield node
        pending.extend(ast.iter_child_nodes(node))


def _is_main(test: ast.expr) -> bool:
    """`if __name__ == "__main__":`, which never runs on import."""
    return (
        isinstance(test, ast.Compare)
        and isinstance(test.left, ast.Name)
        and test.left.id == "__name__"
        and any(isinstance(item, ast.Constant) and item.value == "__main__" for item in test.comparators)
    )


def _is_type_checking(test: ast.expr) -> bool:
    return (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
        isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
    )


def _imports(source: bytes, module: str, is_package: bool) -> set[str]:
    """The modules a source imports when it's imported."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    names: set[str] = set()
    package = module if is_package else module.rpartition(".")[0]
    for node in _module_level(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                parts = package.split(".")
                base_parts = parts[: len(parts) - node.level + 1] if node.level > 1 else parts
                base = ".".join(part for part in base_parts if part)
                target = f"{base}.{node.module}" if node.module else base
            else:
                target = node.module or ""
            if target:
                names.add(target)
                for alias in node.names:
                    names.add(f"{target}.{alias.name}")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "__import__":
            if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                names.add(node.args[0].value)
    return names


def _with_parents(name: str) -> list[str]:
    parts = name.split(".")
    return [".".join(parts[: index + 1]) for index in range(len(parts))]


def _closure(archive: zipfile.ZipFile, roots: Iterable[str]) -> set[str]:
    modules = _module_names(archive)
    kept: set[str] = set()
    pending = [name for root in roots for name in _with_parents(root) if name in modules]
    while pending:
        name = pending.pop()
        if name in kept:
            continue
        kept.add(name)
        path = modules[name]
        for found in _imports(archive.read(path), name, path.endswith("__init__.py")):
            for candidate in _with_parents(found):
                if candidate in modules and candidate not in kept:
                    pending.append(candidate)
    return kept


def roots_from_sources(sources: Iterable[bytes]) -> set[str]:
    """The modules a set of (framework or application) sources import."""
    names: set[str] = set()
    for source in sources:
        names |= _imports(source, "__main__", False)
    return names


def _index(kept: set[str], modules: dict[str, str]) -> list[str]:
    """What the rest holds, compactly: whole top-level names, and `package.*` for packages split in two."""
    rest = set(modules) - kept
    tops = {name.partition(".")[0] for name in kept}
    index: set[str] = set()
    for name in rest:
        top = name.partition(".")[0]
        if top not in tops:
            index.add(top)
        else:
            index.add(name.rpartition(".")[0] + ".*")
    return sorted(index)


def trim(stdlib: bytes, sources: Iterable[bytes], extra: Iterable[str] = ()) -> tuple[bytes, bytes, list[str]]:
    """Split `stdlib` into `(trimmed, rest, index of the rest)` for an app made of `sources`."""
    with zipfile.ZipFile(io.BytesIO(stdlib)) as archive:
        modules = _module_names(archive)
        whole = {name for name in modules if name.partition(".")[0] in WHOLE_PACKAGES}
        roots = set(BOOT_MODULES) | whole | roots_from_sources(sources) | set(extra)
        kept = _closure(archive, roots)
        kept_files = {modules[name] for name in kept}
        trimmed, rest = io.BytesIO(), io.BytesIO()
        with (
            zipfile.ZipFile(trimmed, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as keep,
            zipfile.ZipFile(rest, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as other,
        ):
            for info in archive.infolist():
                if info.is_dir():
                    continue
                data = archive.read(info)
                entry = zipfile.ZipInfo(info.filename, info.date_time)
                entry.compress_type = zipfile.ZIP_DEFLATED
                entry.external_attr = info.external_attr
                is_module = info.filename.endswith(".py")
                # Data files (and anything that isn't a module) stay with the library.
                (keep if not is_module or info.filename in kept_files else other).writestr(entry, data)
    return trimmed.getvalue(), rest.getvalue(), _index(kept, modules)


def _cache_dir() -> Path:
    root = Path.home() / ".cache" / "wybthon"
    if sys.platform == "darwin":
        root = Path.home() / "Library" / "Caches" / "wybthon"
    return root


def fetch_stdlib(pyodide_url: str) -> bytes | None:
    """Pyodide's `python_stdlib.zip` for a release, from a local cache or the network; `None` if unavailable."""
    key = hashlib.sha256(pyodide_url.encode()).hexdigest()[:16]
    cached = _cache_dir() / "stdlib" / f"{key}.zip"
    if cached.is_file():
        return cached.read_bytes()
    if pyodide_url.startswith(("http://", "https://")):
        try:
            with urllib.request.urlopen(pyodide_url + "python_stdlib.zip", timeout=30) as response:
                data: bytes = response.read()
        except OSError:
            return None
    else:
        path = Path(pyodide_url) / "python_stdlib.zip"
        if not path.is_file():
            return None
        data = path.read_bytes()
    try:
        zipfile.ZipFile(io.BytesIO(data)).testzip()
    except zipfile.BadZipFile:
        return None
    cached.parent.mkdir(parents=True, exist_ok=True)
    cached.write_bytes(data)
    return data
