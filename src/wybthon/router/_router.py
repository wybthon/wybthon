"""`create_router`: the route tree, its outlet levels, and plain-anchor navigation."""

from __future__ import annotations

import asyncio
import functools
import inspect
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal
from urllib.parse import urlsplit

from .. import events
from .. import server_functions as _sf
from ..component import component
from ..context import Context, create_context, use_context
from ..reactivity import _core
from ..reactivity._core import Accessor, Memo, _unwrap, untrack
from ..reactivity._primitives import create_memo
from ..reactivity._props import Props, prop
from ..request import http_status
from ..vnode import VNode, h
from ._data import _apply_revalidation
from ._location import SearchParams, navigate, split_url, url, use_location
from ._match import resolve, strip_base

__all__ = [
    "Route",
    "RouteProps",
    "PreloadArgs",
    "Router",
    "create_router",
    "Outlet",
    "use_params",
    "use_search_params",
    "use_route_matches",
    "use_link_state",
    "LinkState",
    "preload_route",
]


@dataclass(frozen=True, slots=True)
class PreloadArgs:
    """What a route's `preload` function receives.

    Attributes:
        params: The matched path parameters.
        location: The URL being preloaded (path, query, and hash).
        intent: `"initial"` (the first render, on the server or while
            hydrating), `"navigate"` (the router is going there), or
            `"preload"` (a link the pointer rests on, or `preload_route`).
    """

    params: dict[str, str]
    location: str
    intent: Literal["initial", "navigate", "preload"]


@dataclass(eq=False)
class Route:
    """A route: a path pattern, the component it shows, and nested routes.

    Patterns are literals, `:name` parameters, optional `:name?`
    parameters, and a final `*name` catch-all (`"*404"` matches anything).
    A child's path continues its parent's, and a route with children is a
    layout: it renders when one of its children matches, with that child
    as its `children` prop (and as [`Outlet()`][wybthon.router.Outlet]).
    A route with no component renders its children directly.

    Attributes:
        path: The path pattern.
        component: The component to show. It receives `params`, `search`,
            `data`, and `children` props (see
            [`RouteProps`][wybthon.router.RouteProps]).
        children: Nested routes.
        preload: Called with [`PreloadArgs`][wybthon.router.PreloadArgs]
            when the route is about to show, or when a link to it is
            preloaded. Warm the route's queries here. Its result, once
            any awaitable it returns resolves, is the component's `data`.
    """

    path: str = ""
    component: Any = None
    children: list[Route] = field(default_factory=list)
    preload: Callable[[PreloadArgs], Any] | None = None


class RouteProps(Props):
    """Props for a route's component. Subclass it to add your own fields.

    Attributes:
        params: The matched path parameters. Navigating between URLs the
            same route matches updates them in place instead of remounting.
        search: The parsed query string.
        data: What the route's `preload` returned (resolved).
        children: The matched child route, for a layout.
    """

    params: dict[str, str] = prop(default_factory=dict)
    search: SearchParams = prop(default_factory=SearchParams)
    data: Any = None
    children: Any = None


class _RouterState:
    __slots__ = ("router", "params", "search", "matches", "base", "preload")

    def __init__(
        self,
        router: Router,
        params: Accessor[dict[str, str]],
        search: Accessor[SearchParams],
        matches: Accessor[list[Route]],
    ) -> None:
        self.router = router
        self.params = params
        self.search = search
        self.matches = matches
        self.base = router.base
        self.preload: Callable[[str, str], Any] | None = None


_RouteContext: Context[_RouterState | None] = create_context(None, name="Router")
_OutletContext: Context[Any] = create_context(None, name="Outlet")


class Router:
    """A route tree; returned by [`create_router`][wybthon.router.create_router].

    Call it to render: `router()`, or `router(root=Shell)` with a root
    layout component that stays mounted and receives the matched route as
    its `children`.

    Attributes:
        routes: The route tree.
        base: The base path the router matches under.
    """

    def __init__(self, routes: list[Route], base: str, preload_links: bool) -> None:
        self.routes = routes
        self.base = base.rstrip("/")
        self.preload_links = preload_links

    def match(self, href: str) -> list[Route]:
        """The routes `href` shows, root to leaf (`[]` when nothing matches); no rendering involved."""
        result = resolve(self.routes, href, self.base)
        return list(result[1]["matches"]) if result is not None else []

    def __call__(self, root: Any = None) -> VNode:
        return h(_RouterView, {"router": self, "root": root})

    def __repr__(self) -> str:
        return f"Router({len(self.routes)} routes, base={self.base or '/'!r})"


def create_router(routes: list[Route], *, base: str = "", preload_links: bool = True) -> Router:
    """Create the app's router from its route tree, as Solid Router 2.0's `createRouter` does.

    The router follows plain `<a href>` links: a click on a same-origin
    link under the base path navigates with the History API instead of
    loading a page. Clicks with a modifier key, links with a `target`,
    `download`, or `rel="external"`, and other origins are left to the
    browser. With `preload_links`, resting the pointer on a link (or
    focusing it) preloads its route's code and data.

    ```python
    router = create_router([
        Route("/", Home),
        Route("/users/:id", User, preload=lambda args: get_user(int(args.params["id"]))),
        Route("*404", NotFound),
    ])

    def app():
        return router(root=Shell)
    ```

    Args:
        routes: The route tree (see [`Route`][wybthon.router.Route]), or
            [`file_routes()`][wybthon.router.file_routes].
        base: The base path the app is served under. Links and
            `navigate` take full paths, as everywhere in HTML.
        preload_links: Preload a link's route when the pointer rests on it.

    Returns:
        A [`Router`][wybthon.router.Router]; call it to render.
    """
    return Router(list(routes), base, preload_links)


class _RouterViewProps(Props):
    _wyb_internal = True
    router: Any = None
    root: Any = None


def _same_app(href: str, base: str) -> str | None:
    """The in-app path for a link's resolved URL, or `None` when the browser should handle it."""
    parts = urlsplit(href)
    path = parts.path or "/"
    if strip_base(path, base) is None:
        return None
    return path + ("?" + parts.query if parts.query else "") + ("#" + parts.fragment if parts.fragment else "")


def _follow(router: Router, preload: Callable[[str, str], Any]) -> Callable[[], None]:
    """Install the router's default handling of links and forms; returns its removal."""

    def link_target(info: dict[str, Any]) -> str | None:
        if not info.get("sameOrigin"):
            return None
        if info.get("download") or info.get("target") not in (None, "", "_self"):
            return None
        if "external" in (info.get("rel") or "").split():
            return None
        href = info.get("href") or ""
        if href.startswith("#"):
            return None
        return _same_app(str(info.get("url") or href), router.base)

    def on_click(evt: events.DomEvent, info: dict[str, Any]) -> None:
        if evt.button != 0 or evt.meta_key or evt.ctrl_key or evt.shift_key or evt.alt_key:
            return
        target = link_target(info)
        if target is None:
            return
        evt.prevent_default()
        navigate(target)

    def on_intent(evt: events.DomEvent, info: dict[str, Any]) -> None:
        if info.get("preload") == "false":
            return
        target = link_target(info)
        if target is not None:
            preload(target, "preload")

    removers = [events.intercept("click", on_click)]
    if router.preload_links:
        removers += [events.intercept("pointerover", on_intent), events.intercept("focusin", on_intent)]

    def remove() -> None:
        for remover in removers:
            remover()

    return remove


@component
def _RouterView(props: _RouterViewProps) -> Any:
    router: Router = untrack(lambda: props.router)
    root = untrack(lambda: props.root)

    def location() -> tuple[str, str, str]:
        return split_url(url())

    pathname = create_memo(lambda: location()[0])
    search = create_memo(lambda: SearchParams(location()[1]))

    def resolved() -> Any:
        result = resolve(router.routes, pathname(), router.base)
        return result[1] if result is not None else {"params": {}, "matches": []}

    match = create_memo(resolved)
    # The page the URL names: a change of hash alone doesn't preload anything again.
    page = create_memo(lambda: _without_hash(url()))
    matches = create_memo(lambda: match()["matches"])
    params = create_memo(lambda: match()["params"])
    state = _RouterState(router, params, search, matches)
    warmed: dict[tuple[int, str], Any] = {}
    first = [True]

    def preload_path(path: str, intent: str = "preload") -> Any:
        result = resolve(router.routes, path, router.base)
        if result is None:
            return None
        _, info = result
        tasks = []
        for route in info["matches"]:
            loader = getattr(route.component, "preload", None)
            if loader is not None and callable(loader):
                loader()
            if route.preload is None:
                continue
            key = (id(route), _without_hash(path))
            if key not in warmed or intent != "preload" and _failed(warmed[key]):
                value = route.preload(PreloadArgs(dict(info["params"]), path, intent))  # type: ignore[arg-type]
                if inspect.isawaitable(value):
                    value = asyncio.ensure_future(value)
                    value.add_done_callback(functools.partial(_forget_failure, warmed, key))
                warmed[key] = value
                if len(warmed) > 64:
                    removed = warmed.pop(next(iter(warmed)))
                    if isinstance(removed, asyncio.Future) and not removed.done():
                        removed.cancel()
            value = warmed[key]
            if isinstance(value, asyncio.Future) and not value.done():
                tasks.append(value)
        if tasks:

            async def wait() -> None:
                await asyncio.gather(*(asyncio.shield(task) for task in tasks), return_exceptions=True)

            return wait()
        return None

    state.preload = preload_path

    def data_for(route: Route) -> Any:
        value = warmed.get((id(route), page()))
        if isinstance(value, asyncio.Future):
            return value.result() if value.done() and not value.cancelled() and value.exception() is None else None
        return value

    def ready() -> Any:
        path = page()
        intent = "initial" if first[0] else "navigate"
        first[0] = False
        value = preload_path(path, intent)
        if inspect.isawaitable(value):

            async def wait() -> bool:
                await value
                return True

            return wait()
        return True

    readiness = create_memo(ready)

    def level(depth: int) -> Any:
        def outlet() -> Any:
            readiness()
            chain = matches()
            if depth >= len(chain):
                if depth == 0:
                    # Nothing matched: the page is a 404.
                    http_status(404)
                return None
            matched = chain[depth]
            return h(
                _RouteEntry,
                {"route": matched, "state": state, "depth": depth, "data_for": data_for, "key": id(matched)},
            )

        return _OutletContext(lambda: level(depth + 1), outlet)

    if not _core._server_depth:
        remove = _follow(router, preload_path)
        _core._current_owner._add_cleanup(remove)

    def cleanup() -> None:
        for value in warmed.values():
            if isinstance(value, asyncio.Future) and not value.done():
                value.cancel()
        warmed.clear()

    _core._current_owner._add_cleanup(cleanup)
    content = level(0)
    if root is not None:
        return _RouteContext(state, h(root, {"children": lambda: content}))
    return _RouteContext(state, content)


def _without_hash(href: str) -> str:
    return href.partition("#")[0]


def _failed(value: Any) -> bool:
    return isinstance(value, asyncio.Future) and value.done() and (value.cancelled() or value.exception() is not None)


def _forget_failure(warmed: dict[tuple[int, str], Any], key: tuple[int, str], done: asyncio.Future[Any]) -> None:
    if (done.cancelled() or done.exception() is not None) and warmed.get(key) is done:
        warmed.pop(key, None)


class _RouteEntryProps(Props):
    _wyb_internal = True
    route: Any = None
    state: Any = None
    depth: Any = 0
    data_for: Any = None


@component
def _RouteEntry(props: _RouteEntryProps) -> Any:
    route: Route = untrack(lambda: props.route)
    state: _RouterState = untrack(lambda: props.state)
    data_for = untrack(lambda: props.data_for)
    # A departing route keeps its last inputs until it unmounts: preparing the
    # destination mustn't hand its still-mounted predecessor missing params.
    params = create_memo(lambda previous: state.params() if route in state.matches() else (previous or {}))
    search = create_memo(lambda previous: state.search() if route in state.matches() else (previous or SearchParams()))
    data = create_memo(lambda: data_for(route))
    child = use_context(_OutletContext)
    if route.component is None:
        return child
    return h(route.component, {"params": params, "search": search, "data": data, "children": child})


@component
def _Outlet() -> Any:
    return use_context(_OutletContext)


_Outlet.__name__ = "Outlet"


def Outlet() -> VNode:
    """The matched child route, inside a layout route's component (the same as its `children` prop)."""
    return h(_Outlet)


def _state() -> _RouterState | None:
    return use_context(_RouteContext)


def use_params() -> Accessor[dict[str, str]]:
    """Tracked accessor for the matched route's path parameters (`{}` outside a router)."""
    state = _state()
    if state is None:
        return Memo(lambda: {})
    return state.params


def use_search_params() -> tuple[Accessor[SearchParams], Callable[..., None]]:
    """The parsed query string, and a function that updates it.

    The setter merges its changes into the current query (`None` or `""`
    removes a key) and navigates without scrolling:

    ```python
    search, set_search = use_search_params()
    set_search(page=int(search().get("page", "1")) + 1)
    ```
    """
    state = _state()
    accessor: Accessor[SearchParams] = state.search if state is not None else Memo(lambda: use_location().query)

    def set_search(changes: dict[str, Any] | None = None, /, *, replace: bool = False, **kwargs: Any) -> None:
        merged = {**(changes or {}), **kwargs}
        path, query, fragment = split_url(url.peek())
        updated = SearchParams(query).merged(merged)
        navigate(
            path + ("?" + updated if updated else "") + ("#" + fragment if fragment else ""),
            replace=replace,
            scroll=False,
        )

    return accessor, set_search


def use_route_matches() -> Accessor[list[Route]]:
    """Tracked accessor for the routes the URL shows, root to leaf."""
    state = _state()
    if state is None:
        return Memo(lambda: [])
    return state.matches


@dataclass(frozen=True, slots=True)
class LinkState:
    """Whether a link's target is the current page; returned by [`use_link_state`][wybthon.router.use_link_state].

    Attributes:
        active: Tracked accessor: the current path is the link's path, or
            (unless `end`) below it. The base path only matches exactly.
        current: Tracked accessor: same path and same query, ignoring the
            hash and parameter order (what `aria-current="page"` means).
    """

    active: Accessor[bool]
    current: Accessor[bool]


def use_link_state(href: str | Callable[[], str], *, end: bool = False) -> LinkState:
    """Whether a link to `href` is active or current, for styling navigation.

    ```python
    @component
    def NavLink(props: NavLinkProps):
        state = use_link_state(lambda: props.href)
        return html(t'<a href={props.href} class={"active" if state.active() else ""}
                       aria-current={"page" if state.current() else None}>{props.children}</a>')
    ```
    """
    state = _state()
    base = state.base if state is not None else ""

    def target() -> tuple[str, str, str]:
        return split_url(_unwrap(href))

    def active() -> bool:
        current = split_url(url())[0].rstrip("/") or "/"
        wanted = target()[0].rstrip("/") or "/"
        if current == wanted:
            return True
        if end or wanted == (base or "/"):
            return False
        return current.startswith(wanted + "/")

    def current() -> bool:
        path, query, _ = split_url(url())
        wanted_path, wanted_query, _ = target()
        return (path.rstrip("/") or "/") == (wanted_path.rstrip("/") or "/") and sorted(
            SearchParams(query)._pairs
        ) == sorted(SearchParams(wanted_query)._pairs)

    return LinkState(Memo(active), Memo(current))


def preload_route(href: str) -> Any:
    """Preload the code and data of the route `href` shows; returns an awaitable, or `None`."""
    state = _state()
    if state is None or state.preload is None:
        return None
    return state.preload(href, "preload")


def _install_hooks() -> None:
    def navigate_to(target: str, replace: bool) -> None:
        if urlsplit(target).netloc:
            _sf._no_navigate(target, replace)
        else:
            navigate(target, replace=replace)

    _sf._set_hooks(_apply_revalidation, navigate_to)


_install_hooks()
