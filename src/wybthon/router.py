"""Client-side router components and navigation helpers for Pyodide apps.

This module exposes the browser-facing router built on top of
[`router_core`][wybthon.router_core]:

- [`Route`][wybthon.Route]: declarative mapping of a path pattern to
  a component, optionally with nested children.
- [`Router`][wybthon.Router]: function component that renders the
  matched route's component and provides the
  [`BasePath`][wybthon.router.BasePath] context.
- [`Link`][wybthon.Link]: anchor element that navigates via the
  History API and toggles an active class.
- [`navigate`][wybthon.navigate]: programmatic navigation helper.
- [`current_path`][wybthon.current_path]: a [`Signal`][wybthon.Signal]
  containing the current pathname plus query string.

See Also:
    - [Routing guide](../concepts/router.md)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from .context import Provider, create_context, use_context
from .reactivity import Signal
from .router_core import resolve as _resolve_core
from .vnode import VNode, dynamic, h

__all__ = ["Route", "Router", "Link", "navigate", "current_path"]


def _current_url() -> str:
    """Return the current pathname plus search string, or `"/"` on failure."""
    try:
        from js import window

        return str(window.location.pathname) + str(window.location.search)
    except Exception:
        return "/"


current_path: Signal[str] = Signal(_current_url())
"""Signal containing the current pathname plus query string.

Updated by [`navigate`][wybthon.navigate] and by the global `popstate`
listener (back/forward navigation). Read it inside reactive scopes to
re-render when the URL changes.
"""

_popstate_proxy: Any = None


def _install_popstate() -> None:
    """Install the `popstate` listener once when running in a browser."""
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
    """Programmatically change the current path and update `current_path`.

    Args:
        path: Target URL path, including any query string.
        replace: When `True`, use `history.replaceState` so the
            current history entry is overwritten instead of appended.
    """
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
    """Parse a query string like `"?a=1&b=2"` into a dict, decoding values."""
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
    """Decode a URL-encoded component if `decodeURIComponent` is available."""
    try:
        from js import decodeURIComponent

        return str(decodeURIComponent(s))
    except Exception:
        return s


@dataclass
class Route:
    """Declarative route definition mapping a path to a component.

    Attributes:
        path: Route pattern (e.g., `"/users/:id"`, `"/docs/*"`).
        component: A function component or class to render when the
            path matches.
        children: Optional nested routes whose paths are joined with
            this route's `path`.
    """

    path: str
    component: Union[Callable[[Dict[str, Any]], VNode], type]
    children: Optional[List["Route"]] = None


def _resolve(routes: List[Route], pathname: str, base_path: str = "") -> Optional[Tuple[Route, Dict[str, Any]]]:
    """Resolve the current route via [`router_core.resolve`][wybthon.router_core.resolve]."""
    return _resolve_core(routes, pathname, base_path)


BasePath = create_context("")
"""Context used by the router to expose the active base path.

[`Link`][wybthon.Link] reads this context so that relative `to` paths
are resolved against the same base path the surrounding
[`Router`][wybthon.Router] is mounted under.
"""


def Router(props: Any) -> Any:
    """Function component that renders the matched route's component.

    The render function is wrapped in a reactive hole so that updates
    to [`current_path`][wybthon.current_path] automatically
    re-evaluate the matched route; no parent re-render is required.

    Args:
        props: The component's props with the following keys:

            - `routes` (`List[Route]`): Declared routes.
            - `base_path` (`str`): Base path stripped before matching.
            - `not_found`: Optional component rendered when no route
              matches. Falls back to a literal `"Not Found"`
              `<div>`.

    Returns:
        A reactive [`VNode`][wybthon.VNode] containing the matched
        component, wrapped in a [`Provider`][wybthon.Provider] that
        publishes the active `base_path` via
        [`BasePath`][wybthon.router.BasePath].
    """

    def render() -> VNode:
        routes: List[Route] = props.value("routes", []) or []
        base_path: str = props.value("base_path", "") or ""
        path = current_path.get()

        if "?" in path:
            pathname, search = path.split("?", 1)
            search = "?" + search
        else:
            pathname, search = path, ""
        query = _parse_query(search)

        resolved = _resolve(routes, pathname, base_path)
        if resolved is None:
            not_found = props.value("not_found")
            if not_found is not None:
                return h(not_found, {"query": query, "params": {}})
            return h("div", {}, "Not Found")

        matched_route, info = resolved
        info["query"] = query

        comp = matched_route.component
        route_props = {**info}
        return h(Provider, {"context": BasePath, "value": base_path}, h(comp, route_props))

    return dynamic(render)


Router._wyb_component = True  # type: ignore[attr-defined]


def Link(props: Any) -> Any:
    """Anchor element component that navigates via the History API.

    Wrapped in a reactive hole so the active class flips
    automatically when the route changes; no parent re-render is
    required. Modifier-key clicks (Cmd/Ctrl/Shift) and middle-clicks
    are passed through to the browser so users can open links in a
    new tab.

    Args:
        props: The component's props with the following keys:

            - `to` (`str`): Target path. Joined with the active base
              path unless it starts with `http://`, `https://`, or
              `#`.
            - `replace` (`bool`): When `True`, replace the current
              history entry instead of pushing a new one.
            - `class_active` (`str`): Class added when `to` matches
              the current path. Defaults to `"active"`.
            - `base_path` (`str`): Override for the base path.
              Defaults to the value provided by the surrounding
              `Router`.
            - `class` / `class_` / `className`: Recognized class
              spellings, merged with the active class when applicable.
            - All other props are forwarded to the underlying `<a>`
              element.

    Returns:
        A reactive [`VNode`][wybthon.VNode] for the anchor element.
    """
    from .events import DomEvent

    base_path_ctx = use_context(BasePath) or ""

    def _with_base(target: str, base_path: str) -> str:
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

    _reserved = {
        "to",
        "replace",
        "class_active",
        "base_path",
        "children",
        "class",
        "className",
        "class_",
        "href",
        "on_click",
    }

    def render() -> VNode:
        to = props.value("to", "/")
        replace = bool(props.value("replace", False))
        class_active = props.value("class_active", "active")
        base_path = props.value("base_path") or base_path_ctx or ""

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
            href = _with_base(to, base_path)
            navigate(href, replace=replace)

        try:
            current = current_path.get()
        except Exception:
            current = "/"
        href_no_search = _with_base(to, base_path)
        if "?" in current:
            current_no_search = current.split("?", 1)[0]
        else:
            current_no_search = current

        is_active = current_no_search == href_no_search

        existing_class = props.value("class") or props.value("class_") or props.value("className")
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

        for k in list(props):
            if k in _reserved:
                continue
            attrs[k] = props.value(k)
        children = props.value("children", [])
        if children is None:
            children = []
        if not isinstance(children, list):
            children = [children]
        return h("a", attrs, *children)

    return dynamic(render)


Link._wyb_component = True  # type: ignore[attr-defined]
