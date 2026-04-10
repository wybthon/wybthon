"""Client-side router components and navigation helpers for Pyodide apps."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from .context import Provider, create_context, use_context
from .reactivity import Signal
from .router_core import resolve as _resolve_core
from .vnode import VNode, h

__all__ = ["Route", "Router", "Link", "navigate", "current_path"]


def _current_url() -> str:
    """Return current pathname+search from the window, or "/" on failure."""
    try:
        from js import window

        return str(window.location.pathname) + str(window.location.search)
    except Exception:
        return "/"


current_path: Signal[str] = Signal(_current_url())

_popstate_proxy: Any = None


def _install_popstate() -> None:
    """Install the popstate listener (once) if running in a browser."""
    global _popstate_proxy
    if _popstate_proxy is not None:
        return
    try:
        from js import window
        from pyodide.ffi import create_proxy

        def _on_popstate(_evt: Any) -> None:
            current_path.set(_current_url())

        _popstate_proxy = create_proxy(_on_popstate)
        window.addEventListener("popstate", _popstate_proxy)
    except Exception:
        pass


_install_popstate()


def navigate(path: str, *, replace: bool = False) -> None:
    """Programmatically change the current path and update `current_path`."""
    try:
        from js import window

        if replace:
            window.history.replaceState(None, "", path)
        else:
            window.history.pushState(None, "", path)
    except Exception:
        pass
    current_path.set(path)


def _parse_query(search: str) -> Dict[str, str]:
    """Parse a query string like "?a=1&b=2" into a dict."""
    if not search or not search.startswith("?"):
        return {}
    out: Dict[str, str] = {}
    for part in search[1:].split("&"):
        if not part:
            continue
        if "=" in part:
            k, v = part.split("=", 1)
        else:
            k, v = part, ""
        out[_decode(k)] = _decode(v)
    return out


def _decode(s: str) -> str:
    """Decode a URL-encoded component if available, else return as-is."""
    try:
        from js import decodeURIComponent

        return str(decodeURIComponent(s))
    except Exception:
        return s


@dataclass
class Route:
    """Declarative route definition mapping a path to a component."""

    path: str
    component: Union[Callable[[Dict[str, Any]], VNode], type]
    children: Optional[List["Route"]] = None


def _compile(path: str) -> Tuple[str, List[str]]:
    """Compile a route path into a regex and list of param names."""
    parts = path.strip("/").split("/") if path != "/" else [""]
    names: List[str] = []
    regex_parts: List[str] = []
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


def _escape_re(s: str) -> str:
    """Escape literal path segments for regex use."""
    import re as _re

    return _re.escape(s)


def _match(pathname: str, route: Route) -> Optional[Tuple[Dict[str, str], Route]]:
    """Match a pathname against a route's pattern and return params on success."""
    import re

    regex, names = _compile(route.path)
    m = re.match(regex, pathname)
    if not m:
        return None
    params: Dict[str, str] = {}
    for i, name in enumerate(names, start=1):
        params[name] = m.group(i)
    return params, route


def _resolve(routes: List[Route], pathname: str, base_path: str = "") -> Optional[Tuple[Route, Dict[str, Any]]]:
    """Resolve the current route using core resolution with a safe fallback."""
    try:
        res = _resolve_core(routes, pathname, base_path)
        if res is None:
            return None
        route, info = res
        return route, info
    except Exception:
        for r in routes:
            m = _match(pathname, r)
            if m is not None:
                params, route = m
                return route, {"params": params}
        return None


BasePath = create_context("")


def Router(props: Any) -> Any:
    """Function component that renders the matched route's component.

    Props:
      - routes: List[Route]
      - base_path: str
      - not_found: component to render on 404
    """

    def render() -> VNode:
        routes: List[Route] = props.get("routes", [])
        base_path: str = props.get("base_path", "")
        path = current_path.get()

        if "?" in path:
            pathname, search = path.split("?", 1)
            search = "?" + search
        else:
            pathname, search = path, ""
        query = _parse_query(search)

        resolved = _resolve(routes, pathname, base_path)
        if resolved is None:
            not_found = props.get("not_found")
            if not_found is not None:
                return h(not_found, {"query": query, "params": {}})
            return h("div", {}, "Not Found")

        matched_route, info = resolved
        info["query"] = query

        comp = matched_route.component
        route_props = {**info}
        return h(Provider, {"context": BasePath, "value": base_path}, h(comp, route_props))

    return render


def Link(props: Dict[str, Any]) -> VNode:
    """Anchor element component that navigates via history API without reloads."""
    from .events import DomEvent

    to = props.get("to", "/")
    replace = bool(props.get("replace", False))
    class_active = props.get("class_active", "active")
    base_path: str = props.get("base_path") or use_context(BasePath) or ""

    def _with_base(target: str) -> str:
        if not isinstance(target, str):
            return "/"
        if target.startswith("http://") or target.startswith("https://") or target.startswith("#"):
            return target
        if not base_path:
            return target
        if target.startswith("/"):
            if base_path == "/":
                return target
            return (base_path.rstrip("/") or "/") + target
        if base_path == "/":
            return "/" + target.strip("/")
        return (base_path.rstrip("/") or "") + "/" + target.strip("/")

    def handle_click(evt: DomEvent) -> None:
        try:
            js_evt = evt._js_event
            if (
                getattr(js_evt, "metaKey", False)
                or getattr(js_evt, "ctrlKey", False)
                or getattr(js_evt, "shiftKey", False)
                or getattr(js_evt, "button", 0) != 0
            ):
                return
        except Exception:
            pass
        evt.prevent_default()
        href = _with_base(to)
        navigate(href, replace=replace)

    try:
        current = current_path.get()
    except Exception:
        current = "/"
    href_no_search = _with_base(to)
    if "?" in current:
        current_no_search = current.split("?", 1)[0]
    else:
        current_no_search = current

    is_active = current_no_search == href_no_search

    existing_class = props.get("class") or props.get("className")
    classes: List[str] = []
    if isinstance(existing_class, str) and existing_class.strip():
        classes.append(existing_class)
    elif isinstance(existing_class, (list, tuple)):
        classes.extend(str(x) for x in existing_class if x)
    if is_active and class_active:
        classes.append(str(class_active))

    attrs: Dict[str, Any] = {"href": href_no_search, "on_click": handle_click}
    if classes:
        attrs["class"] = " ".join(classes)

    _reserved = {"to", "replace", "class_active", "base_path", "children", "class", "className", "href", "on_click"}
    for k, v in props.items():
        if k in _reserved:
            continue
        attrs[k] = v
    children = props.get("children", [])
    if not isinstance(children, list):
        children = [children]
    return h("a", attrs, *children)
