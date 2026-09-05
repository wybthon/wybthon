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
from functools import lru_cache
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import unquote, urlsplit


@dataclass
class RouteSpec:
    """Minimal route spec used for pure-Python resolution in tests and tools.

    Attributes:
        path: Route pattern (e.g., `"/users/:id"`).
        children: Optional nested routes whose paths are joined with
            this route's `path`.
    """

    path: str
    children: Optional[List["RouteSpec"]] = None


def _escape_re(s: str) -> str:
    """Escape path literal fragments for safe regex construction."""
    import re as _re

    return _re.escape(s)


@lru_cache(maxsize=512)
def _compile_pattern(path: str) -> Tuple[str, List[str]]:
    """Compile a route path to a regex and the list of captured param names.

    Patterns may include named params (`:id`), positional wildcards
    (`*`), and a trailing wildcard that also matches the parent path
    without trailing slash (e.g., `"/docs/*"` matches both `"/docs"`
    and `"/docs/intro"`).

    Args:
        path: Route pattern (e.g., `"/users/:id"`, `"/docs/*"`).

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
        pathname: Concrete URL path (e.g., `"/users/42"`).
        pattern: Route pattern (e.g., `"/users/:id"`).

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
        params[name] = unquote(m.group(i) or "")
    return params


def _join(parent: str, child: str) -> str:
    """Join a parent and child path, handling root and slash normalization."""
    if child.startswith("/"):
        return child
    if parent == "/":
        return "/" + child.strip("/")
    return parent.rstrip("/") + "/" + child.strip("/")


def resolve(routes: List[Any], pathname: str, base_path: str = "") -> Optional[Tuple[Any, Dict[str, Any]]]:
    """Resolve a pathname to the best matching route and params.

    The router prefers the most specific segment match and honors a
    `base_path` prefix when provided.

    Args:
        routes: Flat or nested route specs (any object exposing
            `path` and optional `children`).
        pathname: The current URL pathname.
        base_path: Optional base path stripped from `pathname` before
            matching. When `pathname` doesn't start with `base_path`,
            the function returns `None`.

    Returns:
        A tuple `(route, payload)` where `payload` contains a
        `"params"` dict, or `None` when no route matches.
    """
    pathname = urlsplit(pathname).path or "/"
    if pathname != "/":
        pathname = pathname.rstrip("/")
    if base_path:
        base = base_path.rstrip("/") or "/"
        if base != "/":
            if pathname != base and not pathname.startswith(base + "/"):
                return None
            pathname = "/" + pathname[len(base) :].lstrip("/")

    candidates: list[tuple[str, Any, list[Any]]] = []

    def walk(items: Iterable[Any], parent: str, chain: list[Any]) -> None:
        for route in items:
            full = _join(parent, getattr(route, "path", ""))
            lineage = [*chain, route]
            candidates.append((full, route, lineage))
            walk(getattr(route, "children", None) or [], full, lineage)

    walk(routes, "/", [])
    best: Any = None
    for full, route, chain in candidates:
        params = _match_path(pathname, full)
        if params is None:
            continue
        # Segment order matters: static literals beat parameters, which beat
        # wildcards. An exact endpoint beats its optional wildcard extension.
        segments = full.strip("/").split("/") if full != "/" else []
        score = tuple(0 if part == "*" else 1 if part.startswith(":") else 2 for part in segments)
        rank = (*score, 3)
        if best is None or rank > best[0] or (rank == best[0] and len(chain) > len(best[3])):
            best = rank, route, params, chain
    if best is None:
        return None
    _, route, params, chain = best
    return route, {"params": params, "matches": chain}
