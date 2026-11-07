"""File-based routes: a directory of route modules becomes a route tree.

```
app/routes/
    _layout.py        the root layout (optional)
    index.py          /
    about.py          /about
    users/
        _layout.py    a layout for everything under /users
        index.py      /users
        [id].py       /users/:id
        [[tab]].py    /users/:tab?   (optional parameter)
    (marketing)/      a group: organizes files without adding a segment
        pricing.py    /pricing
    [...404].py       anything else
```

A page module defines a `Page` component, and may define
`preload(args)` (see [`PreloadArgs`][wybthon.router.PreloadArgs]). A
`_layout.py` defines a `Layout` component, which receives the matched
page as its `children`. Any route module may also define HTTP handlers
(`async def GET(event)`, `POST`, `PUT`, `PATCH`, `DELETE`), which
[`wybthon.asgi`][wybthon.asgi] serves at the route's URL for requests
that aren't page loads; the build removes them from the browser's copy.
Other files starting with `_` are private to the directory.

Pages load lazily: a route's module is imported the first time the
route shows (or is preloaded), so a page's startup imports only what it
shows.
"""

from __future__ import annotations

import importlib
import importlib.util
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

from ._router import PreloadArgs, Route

__all__ = ["file_routes", "api_routes", "ApiRoute", "load_route_module"]

_PAGE = re.compile(r"^(?:async\s+def|def|class)\s+Page\b|^Page\s*[:=]", re.M)
_LAYOUT = re.compile(r"^(?:async\s+def|def|class)\s+Layout\b|^Layout\s*[:=]", re.M)
_PRELOAD = re.compile(r"^(?:async\s+)?def\s+preload\b|^preload\s*[:=]", re.M)
_HANDLER = re.compile(r"^(?:async\s+)?def\s+(GET|POST|PUT|PATCH|DELETE)\b", re.M)


def _segment(stem: str) -> str | None:
    """A file or directory name's path segment: `None` for a group, `""` for an index."""
    if stem == "index":
        return ""
    if stem.startswith("(") and stem.endswith(")"):
        return None
    if stem.startswith("[[") and stem.endswith("]]"):
        return f":{stem[2:-2]}?"
    if stem.startswith("[...") and stem.endswith("]"):
        return f"*{stem[4:-1]}"
    if stem.startswith("[") and stem.endswith("]"):
        return f":{stem[1:-1]}"
    return stem


def _module_part(stem: str) -> str:
    """An importable stand-in for a file or directory name."""
    if stem.isidentifier():
        return stem
    return "_wyb_" + re.sub(r"\W", lambda found: f"_{ord(found.group()):x}_", stem)


def _package_directory(package: str) -> Path:
    spec = importlib.util.find_spec(package)
    if spec is None or not spec.submodule_search_locations:
        raise ValueError(f"file_routes needs a package of route modules; {package!r} isn't one")
    return Path(next(iter(spec.submodule_search_locations)))


def load_route_module(package: str, relative: tuple[str, ...]) -> ModuleType:
    """Import a route module by its path under the routes package, with Wybthon's compiler."""
    name = ".".join([package, *(_module_part(part) for part in relative)])
    module = sys.modules.get(name)
    if module is not None:
        return module
    if all(part.isidentifier() for part in relative):
        return importlib.import_module(name)
    directory = _package_directory(package)
    path = directory.joinpath(*relative[:-1], relative[-1] + ".py")
    parent = name.rpartition(".")[0]
    if parent not in sys.modules:
        parent_relative = relative[:-1]
        if parent_relative and not all(part.isidentifier() for part in parent_relative):
            _namespace(parent, directory.joinpath(*parent_relative))
        else:
            importlib.import_module(parent)
    from .._hook import _Loader

    loader = _Loader(name, str(path))
    spec = importlib.util.spec_from_file_location(name, path, loader=loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        loader.exec_module(module)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return module


def _namespace(name: str, path: Path) -> None:
    parent = name.rpartition(".")[0]
    if parent and parent not in sys.modules:
        _namespace(parent, path.parent)
    module = ModuleType(name)
    module.__path__ = [str(path)]
    sys.modules[name] = module


def _lazy_export(package: str, relative: tuple[str, ...], export: str) -> Any:
    from ..lazy import lazy

    def load() -> Any:
        return getattr(load_route_module(package, relative), export)

    return lazy(load)


def _preloader(package: str, relative: tuple[str, ...]) -> Any:
    def preload(args: PreloadArgs) -> Any:
        hook = getattr(load_route_module(package, relative), "preload", None)
        return hook(args) if callable(hook) else None

    return preload


def _scan(package: str, directory: Path, relative: tuple[str, ...]) -> list[Route]:
    routes: list[Route] = []
    layout: Path | None = None
    entries = sorted(directory.iterdir(), key=lambda path: (path.is_dir(), path.name))
    for path in entries:
        if path.name == "__pycache__" or path.name.startswith("."):
            continue
        if path.is_dir():
            segment = _segment(path.name)
            children = _scan(package, path, (*relative, path.name))
            if not children:
                continue
            nested_layout = next((route for route in children if getattr(route, "_wyb_layout", False)), None)
            if nested_layout is not None:
                nested_layout.path = segment or ""
                routes.append(nested_layout)
            else:
                routes.append(Route(segment or "", None, children))
            continue
        if path.suffix != ".py" or path.name == "__init__.py":
            continue
        stem = path.stem
        if stem == "_layout":
            layout = path
            continue
        if stem.startswith("_"):
            continue
        source = path.read_text(encoding="utf-8")
        if not _PAGE.search(source):
            continue
        segment = _segment(stem)
        module_relative = (*relative, stem)
        routes.append(
            Route(
                segment or "",
                _lazy_export(package, module_relative, "Page"),
                preload=_preloader(package, module_relative) if _PRELOAD.search(source) else None,
            )
        )
    # Static segments first, then parameters, then catch-alls (matching ranks them anyway).
    routes.sort(key=lambda route: (route.path.startswith("*"), route.path.startswith(":")))
    if layout is not None:
        source = layout.read_text(encoding="utf-8")
        component = _lazy_export(package, (*relative, "_layout"), "Layout") if _LAYOUT.search(source) else None
        wrapper = Route("", component, routes)
        wrapper._wyb_layout = True  # type: ignore[attr-defined]
        return [wrapper]
    return routes


def file_routes(package: str = "app.routes") -> list[Route]:
    """The route tree for a package of route modules (see the module docs for the layout).

    Args:
        package: The dotted name of the routes package.

    Returns:
        Routes for [`create_router`][wybthon.router.create_router].
    """
    return _scan(package, _package_directory(package), ())


@dataclass(frozen=True, slots=True)
class ApiRoute:
    """A route module's HTTP handlers (server side).

    Attributes:
        path: The route's path pattern.
        methods: The HTTP methods it handles.
        package: The routes package.
        relative: The module's path under the package, without `.py`.
    """

    path: str
    methods: frozenset[str]
    package: str
    relative: tuple[str, ...]

    def handler(self, method: str) -> Any:
        """The module's handler for `method`, imported on first use."""
        return getattr(load_route_module(self.package, self.relative), method, None)


def api_routes(package: str = "app.routes") -> list[ApiRoute]:
    """The HTTP handlers the routes package defines, with their path patterns."""
    found: list[ApiRoute] = []
    root = _package_directory(package)

    def walk(directory: Path, relative: tuple[str, ...], prefix: str) -> None:
        for path in sorted(directory.iterdir()):
            if path.is_dir() and path.name != "__pycache__":
                segment = _segment(path.name)
                walk(path, (*relative, path.name), prefix if not segment else f"{prefix}/{segment}")
            elif path.suffix == ".py" and path.name != "__init__.py" and not path.stem.startswith("_"):
                methods = frozenset(_HANDLER.findall(path.read_text(encoding="utf-8")))
                if methods:
                    segment = _segment(path.stem)
                    pattern = prefix if not segment else f"{prefix}/{segment}"
                    found.append(ApiRoute(pattern or "/", methods, package, (*relative, path.stem)))

    walk(root, (), "")
    return found
