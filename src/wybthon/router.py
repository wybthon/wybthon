from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from js import window
from pyodide.ffi import create_proxy

from .component import Component
from .context import Provider, create_context, use_context
from .events import DomEvent
from .reactivity import signal
from .router_core import resolve as _resolve_core
from .vdom import VNode, h


def _current_url() -> str:
    try:
        return str(window.location.pathname) + str(window.location.search)
    except Exception:
        return "/"


current_path = signal(_current_url())


def _on_popstate(_evt) -> None:
    current_path.set(_current_url())


_popstate_proxy = None

try:
    # Keep a reference to the proxy to prevent GC and event loop invalid state errors
    if _popstate_proxy is None:
        _popstate_proxy = create_proxy(_on_popstate)
        window.addEventListener("popstate", _popstate_proxy)
except Exception:
    pass


def navigate(path: str, *, replace: bool = False) -> None:
    try:
        if replace:
            window.history.replaceState(None, "", path)
        else:
            window.history.pushState(None, "", path)
    except Exception:
        pass
    current_path.set(path)


def _parse_query(search: str) -> Dict[str, str]:
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
    try:
        from js import decodeURIComponent

        return str(decodeURIComponent(s))
    except Exception:
        return s


@dataclass
class Route:
    path: str
    component: Union[Callable[[Dict[str, Any]], VNode], type]
    children: Optional[List["Route"]] = None


def _compile(path: str) -> Tuple[str, List[str]]:
    # Convert patterns like "/users/:id" to regex "^/users/([^/]+)$"
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
    import re as _re

    return _re.escape(s)


def _match(pathname: str, route: Route) -> Optional[Tuple[Dict[str, str], Route]]:
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
    try:
        res = _resolve_core(routes, pathname, base_path)
        if res is None:
            return None
        route, info = res
        return route, info
    except Exception:
        # Fallback to flat matching of top-level routes only
        for r in routes:
            m = _match(pathname, r)
            if m is not None:
                params, route = m
                return route, {"params": params}
        return None


BasePath = create_context("")


class Router(Component):
    def render(self) -> VNode:
        routes: List[Route] = self.props.get("routes", [])
        base_path: str = self.props.get("base_path", "")
        path = current_path.get()
        if "?" in path:
            pathname, search = path.split("?", 1)
            search = "?" + search
        else:
            pathname, search = path, ""
        query = _parse_query(search)

        resolved = _resolve(routes, pathname, base_path)
        if resolved is None:
            not_found = self.props.get("not_found")
            if callable(not_found) and not isinstance(not_found, type):
                vnode = not_found({"query": query, "params": {}})
                if not isinstance(vnode, VNode):
                    vnode = h("div", {}, vnode)
                return vnode
            if isinstance(not_found, type):
                return h(not_found, {**self.props, "query": query, "params": {}})
            return h("div", {}, "Not Found")

        matched_route, info = resolved
        info["query"] = query

        comp = matched_route.component
        props = {**self.props, **info}
        # Function component vs class component
        if callable(comp) and not isinstance(comp, type):
            sub = comp(props)
            if not isinstance(sub, VNode):
                sub = h("div", {}, sub)
            return h(Provider, {"context": BasePath, "value": base_path}, sub)
        return h(Provider, {"context": BasePath, "value": base_path}, h(comp, props))


def Link(props: Dict[str, Any]) -> VNode:
    to = props.get("to", "/")
    # Use explicit base_path prop if provided, otherwise read from context
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
        # relative path; join with base
        if base_path == "/":
            return "/" + target.strip("/")
        return (base_path.rstrip("/") or "") + "/" + target.strip("/")

    def handle_click(evt: DomEvent) -> None:
        try:
            js_evt = evt._js_event
            # Allow new-tab and modified clicks to pass through
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
        navigate(href)

    attrs = {"href": _with_base(to), "on_click": handle_click}
    children = props.get("children", [])
    if not isinstance(children, list):
        children = [children]
    return h("a", attrs, *children)
