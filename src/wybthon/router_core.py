"""Core, browser-agnostic path matching and route resolution helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple


@dataclass
class RouteSpec:
    """Minimal route spec used for pure-Python resolution in tests/tools."""

    path: str
    children: Optional[List["RouteSpec"]] = None


def _escape_re(s: str) -> str:
    """Escape path literal fragments for regex construction."""
    import re as _re

    return _re.escape(s)


def _compile_pattern(path: str) -> Tuple[str, List[str]]:
    """Compile a route path to a regex and list of param names."""
    # Convert patterns like "/users/:id" to regex "^/users/([^/]+)$"
    parts = path.strip("/").split("/") if path != "/" else [""]
    names: List[str] = []
    regex_parts: List[str] = []

    # Special-case trailing wildcard so that "/docs/*" matches both "/docs" and "/docs/..."
    if parts and parts[-1] == "*":
        head_parts = parts[:-1]
        for p in head_parts:
            if p.startswith(":") and len(p) > 1:
                names.append(p[1:])
                regex_parts.append(r"([^/]+)")
            elif p == "*":
                # Non-trailing wildcard: greedy match
                names.append("wildcard")
                regex_parts.append(r"(.*)")
            else:
                regex_parts.append(_escape_re(p))
        regex = r"^/" + "/".join(x for x in regex_parts if x)
        # Optional "/<rest>" with capture
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
    """Try to match a pathname against a pattern, returning params on success."""
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
    """Join a parent and child path, handling root and slashes."""
    if child.startswith("/"):
        return child
    if parent == "/":
        return "/" + child.strip("/")
    return parent.rstrip("/") + "/" + child.strip("/")


def _flatten(routes: Iterable[Any], parent: str = "/") -> List[Tuple[str, Any]]:
    """Flatten nested route specs into (full_path, route) pairs."""
    flat: List[Tuple[str, Any]] = []
    for r in routes:
        full = _join(parent, getattr(r, "path", ""))
        flat.append((full, r))
        children = getattr(r, "children", None) or []
        flat.extend(_flatten(children, full))
    return flat


def resolve(routes: List[Any], pathname: str, base_path: str = "") -> Optional[Tuple[Any, Dict[str, Any]]]:
    """Resolve a pathname to the best matching route and params, honoring base_path."""
    # Trim base_path, if provided
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
        # Prefer the most specific (longest) path
        if best is None or len(full) > len(best[0]):
            best = (full, r, params)

    if best is None:
        return None

    _, route, params = best
    return route, {"params": params}
