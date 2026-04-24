"""Core, browser-agnostic path matching and route resolution helpers.

This module is the algorithmic heart of Wybthon's router. It compiles
route patterns to regular expressions, matches them against a
pathname, and resolves the most specific match. Because it has no
browser dependencies, it can be used in tests, in tooling, and on the
server side.

Public surface:

- [`RouteSpec`][wybthon.router_core.RouteSpec]: minimal dataclass used
  to describe routes for pure-Python tests.
- [`resolve`][wybthon.router_core.resolve]: resolve a pathname to the
  best matching route and params.

See Also:
    - [Routing guide](../concepts/router.md)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple


@dataclass
class RouteSpec:
    """Minimal route spec used for pure-Python resolution in tests and tools.

    Attributes:
        path: Route pattern (e.g. `"/users/:id"`).
        children: Optional nested routes whose paths are joined with
            this route's `path`.
    """

    path: str
    children: Optional[List["RouteSpec"]] = None


def _escape_re(s: str) -> str:
    """Escape path literal fragments for safe regex construction."""
    import re as _re

    return _re.escape(s)


def _compile_pattern(path: str) -> Tuple[str, List[str]]:
    """Compile a route path to a regex and the list of captured param names.

    Patterns may include named params (`:id`), positional wildcards
    (`*`), and a trailing wildcard that also matches the parent path
    without trailing slash (e.g. `"/docs/*"` matches both `"/docs"`
    and `"/docs/intro"`).

    Args:
        path: Route pattern (e.g. `"/users/:id"`, `"/docs/*"`).

    Returns:
        A tuple `(regex, names)` where `regex` is the compiled
        regular expression source and `names` lists capture-group
        names in order.
    """
    parts = path.strip("/").split("/") if path != "/" else [""]
    names: List[str] = []
    regex_parts: List[str] = []

    if parts and parts[-1] == "*":
        head_parts = parts[:-1]
        for p in head_parts:
            if p.startswith(":") and len(p) > 1:
                names.append(p[1:])
                regex_parts.append(r"([^/]+)")
            elif p == "*":
                names.append("wildcard")
                regex_parts.append(r"(.*)")
            else:
                regex_parts.append(_escape_re(p))
        regex = r"^/" + "/".join(x for x in regex_parts if x)
        regex += r"(?:/(.*))?$"
        names.append("wildcard")
        return regex, names

    for p in parts:
        if p.startswith(":") and len(p) > 1:
            names.append(p[1:])
            regex_parts.append(r"([^/]+)")
        elif p == "*":
            names.append("wildcard")
            regex_parts.append(r"(.*)")
        else:
            regex_parts.append(_escape_re(p))
    regex = r"^/" + "/".join(x for x in regex_parts if x)
    regex += r"$"
    return regex, names


def _match_path(pathname: str, pattern: str) -> Optional[Dict[str, str]]:
    """Match `pathname` against `pattern`, returning extracted params.

    Args:
        pathname: Concrete URL path (e.g. `"/users/42"`).
        pattern: Route pattern (e.g. `"/users/:id"`).

    Returns:
        A dict of captured params on a successful match, or `None`.
    """
    import re

    regex, names = _compile_pattern(pattern)
    m = re.match(regex, pathname)
    if not m:
        return None
    params: Dict[str, str] = {}
    for i, name in enumerate(names, start=1):
        params[name] = m.group(i)
    return params


def _join(parent: str, child: str) -> str:
    """Join a parent and child path, handling root and slash normalization."""
    if child.startswith("/"):
        return child
    if parent == "/":
        return "/" + child.strip("/")
    return parent.rstrip("/") + "/" + child.strip("/")


def _flatten(routes: Iterable[Any], parent: str = "/") -> List[Tuple[str, Any]]:
    """Flatten nested route specs into a list of `(full_path, route)` pairs."""
    flat: List[Tuple[str, Any]] = []
    for r in routes:
        full = _join(parent, getattr(r, "path", ""))
        flat.append((full, r))
        children = getattr(r, "children", None) or []
        flat.extend(_flatten(children, full))
    return flat


def resolve(routes: List[Any], pathname: str, base_path: str = "") -> Optional[Tuple[Any, Dict[str, Any]]]:
    """Resolve a pathname to the best matching route and params.

    The router prefers the most specific (longest) match and honors a
    `base_path` prefix when provided.

    Args:
        routes: Flat or nested route specs (any object exposing
            `path` and optional `children`).
        pathname: The current URL pathname.
        base_path: Optional base path stripped from `pathname` before
            matching. When `pathname` does not start with `base_path`,
            the function returns `None`.

    Returns:
        A tuple `(route, payload)` where `payload` contains a
        `"params"` dict, or `None` when no route matches.
    """
    if base_path:
        base = base_path.rstrip("/") or "/"
        if base != "/":
            if not pathname.startswith(base):
                return None
            pathname = "/" + pathname[len(base) :].lstrip("/")

    flat = _flatten(routes, "/")
    best: Optional[Tuple[str, Any, Dict[str, str]]] = None
    for full, r in flat:
        params = _match_path(pathname, full)
        if params is None:
            continue
        if best is None or len(full) > len(best[0]):
            best = (full, r, params)

    if best is None:
        return None

    _, route, params = best
    return route, {"params": params}
