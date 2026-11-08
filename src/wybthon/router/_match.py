"""Path patterns and route matching, with no browser or rendering involved."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache
from typing import Any
from urllib.parse import unquote, urlsplit

__all__ = ["RouteSpec", "match_route", "join_paths"]


@dataclass
class RouteSpec:
    """A route without a component, for matching in tests and tools.

    Attributes:
        path: Route pattern (for example `"/users/:id"`).
        children: Nested routes, whose paths continue this one's.
    """

    path: str
    children: list[RouteSpec] | None = None


@lru_cache(maxsize=512)
def _compile(path: str) -> tuple[re.Pattern[str], tuple[str, ...], tuple[int, ...]]:
    """A pattern's regex, its parameter names, and its specificity score.

    Segments are literals, `:name` parameters, optional `:name?`
    parameters, and a final `*name` (or bare `*`) that captures the rest
    of the path, including nothing, so `/docs/*rest` matches `/docs` too.
    Literals outrank parameters, which outrank the catch-all.
    """
    parts = [part for part in path.strip("/").split("/") if part]
    names: list[str] = []
    score: list[int] = []
    regex = ""
    for index, part in enumerate(parts):
        if part.startswith("*"):
            if index != len(parts) - 1:
                raise ValueError(f"A catch-all must be a route pattern's last segment: {path}")
            names.append(part[1:] or "wildcard")
            regex += r"(?:/(.*))?"
            score.append(0)
        elif part.startswith(":") and part.endswith("?") and len(part) > 2:
            names.append(part[1:-1])
            regex += r"(?:/([^/]+))?"
            score.append(1)
        elif part.startswith(":") and len(part) > 1:
            names.append(part[1:])
            regex += r"/([^/]+)"
            score.append(1)
        else:
            regex += "/" + re.escape(part)
            score.append(2)
    return re.compile("^" + (regex or "/") + "/?$" if regex else r"^/$"), tuple(names), tuple(score)


def match_path(pathname: str, pattern: str) -> dict[str, str] | None:
    """`pathname`'s parameters when it matches `pattern`, else `None`."""
    regex, names, _ = _compile(pattern)
    found = regex.match(pathname)
    if found is None:
        return None
    # A parameter that matched nothing (optional, or an empty catch-all) is "".
    return {name: unquote(value or "") for name, value in zip(names, found.groups())}


def join_paths(parent: str, child: str) -> str:
    """Join a parent route's path with a child's; a child path is always relative, as in Solid."""
    parent = parent.strip("/")
    child = child.strip("/")
    joined = "/".join(part for part in (parent, child) if part)
    return "/" + joined


def strip_base(pathname: str, base: str) -> str | None:
    """`pathname` without the router's base path, or `None` when it's outside it."""
    base = base.rstrip("/")
    if not base:
        return pathname or "/"
    if pathname != base and not pathname.startswith(base + "/"):
        return None
    return "/" + pathname[len(base) :].lstrip("/")


def match_route(routes: list[Any], pathname: str, base_path: str = "") -> tuple[Any, dict[str, Any]] | None:
    """The best matching route for `pathname`, with its parameters and its chain of parents.

    Args:
        routes: Route definitions: anything with a `path` and optional
            `children` ([`Route`][wybthon.router.Route],
            [`RouteSpec`][wybthon.router.RouteSpec]).
        pathname: A URL path (a query or hash is ignored).
        base_path: The router's base path, stripped before matching.

    Returns:
        `(route, {"params": ..., "matches": [root, ..., route]})`, or
        `None` when nothing matches.
    """
    pathname = urlsplit(pathname).path or "/"
    stripped = strip_base(pathname, base_path)
    if stripped is None:
        return None
    best: tuple[tuple[int, ...], int, Any, dict[str, str], list[Any]] | None = None

    def walk(items: Iterable[Any], parent: str, chain: list[Any]) -> None:
        nonlocal best
        for route in items:
            full = join_paths(parent, getattr(route, "path", "") or "")
            lineage = [*chain, route]
            children = getattr(route, "children", None) or []
            params = match_path(stripped, full)
            # A route with children is a layout: it matches through a child
            # (or through a child with an empty path), not on its own.
            if params is not None and not children:
                _, _, score = _compile(full)
                rank = (*score, 3)
                if best is None or rank > best[0] or (rank == best[0] and len(lineage) > best[1]):
                    best = rank, len(lineage), route, params, lineage
            walk(children, full, lineage)

    walk(routes, "/", [])
    if best is None:
        return None
    _, _, route, params, chain = best
    return route, {"params": params, "matches": chain}
