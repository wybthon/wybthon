"""The browser's URL as a signal, navigation, and scroll restoration."""

from __future__ import annotations

from typing import Any
from urllib.parse import parse_qsl, unquote_plus, urlencode, urljoin, urlsplit

from ..reactivity import _core
from ..reactivity._core import Accessor, Signal

__all__ = ["Location", "SearchParams", "navigate", "use_location", "url"]


def _current_url() -> str:
    """The browser's path, query, and hash, or `"/"` outside a browser."""
    try:
        from js import window

        return str(window.location.pathname) + str(window.location.search) + str(getattr(window.location, "hash", ""))
    except Exception:
        return "/"


# The browser's URL. It's read, and the `popstate` listener installed, on
# first use rather than at import: the boot snapshot (RFC 0006) imports this
# module in a worker, which has no `window`, and a restored page must not
# keep the worker's state.
_path: Signal[str] = Signal("/", name="location")
_located = False


def _location() -> Signal[str]:
    global _located
    if not _located:
        _located = True
        # Nothing has read it yet, so there are no observers to notify.
        _path._value = _current_url()
        _install_popstate()
    return _path


class _Url(Accessor[str]):
    """The browser's URL, or the request URL during a server render."""

    __slots__ = ()

    def __call__(self) -> str:
        session = _core._session
        if session is not None and session.url is not None:
            return str(session.url)
        return _location()()

    def peek(self) -> str:
        session = _core._session
        if session is not None and session.url is not None:
            return str(session.url)
        return _location().peek()

    def _label(self) -> str:
        return "url"


url: Accessor[str] = _Url()
"""Tracked accessor for the current path, query, and hash (the request URL on the server)."""

_popstate_proxy: Any = None


def _install_popstate() -> None:
    global _popstate_proxy
    if _popstate_proxy is not None:
        return
    try:
        from js import window
        from pyodide.ffi import create_proxy

        def _on_popstate(_evt: Any) -> None:
            _path._set(_current_url())

            def restore() -> None:
                if (tx := _core._node_tx.get(_path)) is not None:
                    tx.root().reverts.append(lambda: _core._settled_queue.append(_restore_scroll))
                else:
                    _restore_scroll()

            _core._settled_queue.append(restore)
            _core.flush()

        _popstate_proxy = create_proxy(_on_popstate)
        window.addEventListener("popstate", _popstate_proxy)
        window.addEventListener("hashchange", _popstate_proxy)
    except Exception:
        pass


_scroll_positions: dict[str, tuple[float, float]] = {}


def _restore_scroll() -> None:
    try:
        from js import window

        position = _scroll_positions.get(_path.peek(), (0, 0))
        window.scrollTo(*position)
    except ImportError, AttributeError:
        pass


def navigate(path: str, *, replace: bool = False, scroll: bool = True) -> None:
    """Go to `path` within the app, or load it when it's on another origin.

    Relative paths resolve against the current URL. Back and forward
    restore scroll positions; an ordinary navigation scrolls to the hash's
    target, or to the top, once the destination is on screen. A path
    starting with `/` is a full path: the router's base isn't added. A
    no-op while rendering on the server.
    """
    if _core._server_depth:
        return
    _location()
    target = urlsplit(path)
    external = bool(target.scheme or target.netloc)
    try:
        from js import window

        origin = str(window.location.origin)
        if external and target.scheme + "://" + target.netloc != origin:
            window.location.assign(path)
            return
        _scroll_positions[_path.peek()] = (float(getattr(window, "scrollX", 0)), float(getattr(window, "scrollY", 0)))
        if len(_scroll_positions) > 256:
            _scroll_positions.pop(next(iter(_scroll_positions)))
        resolved = urlsplit(urljoin(origin + _current_url(), path))
        canonical = (
            resolved.path
            + ("?" + resolved.query if resolved.query else "")
            + ("#" + resolved.fragment if resolved.fragment else "")
        )
        if replace:
            window.history.replaceState(None, "", canonical)
        else:
            window.history.pushState(None, "", canonical)
    except ImportError, AttributeError:
        if external:
            return
        canonical = urljoin(_path.peek(), path)
    _path._set(canonical)
    if scroll:

        def after_commit() -> None:
            def position() -> None:
                try:
                    from js import document, window

                    fragment = urlsplit(canonical).fragment
                    element = document.getElementById(unquote_plus(fragment)) if fragment else None
                    if element is not None:
                        element.scrollIntoView()
                    else:
                        window.scrollTo(0, 0)
                except ImportError, AttributeError:
                    pass

            if (tx := _core._node_tx.get(_path)) is not None:
                tx.root().reverts.append(lambda: _core._settled_queue.append(position))
            else:
                position()

        _core._settled_queue.append(after_commit)


class SearchParams(dict[str, str]):
    """A decoded query string: each name's last value, plus [`get_all`][wybthon.router.SearchParams.get_all]."""

    def __init__(self, search: str = "") -> None:
        self._pairs = parse_qsl(search.removeprefix("?"), keep_blank_values=True)
        super().__init__(self._pairs)

    def get_all(self, key: str) -> list[str]:
        """Every value of `key`, in URL order."""
        return [value for name, value in self._pairs if name == key]

    def merged(self, changes: dict[str, Any]) -> str:
        """The query string with `changes` applied (`None` or `""` removes a key)."""
        pairs = [(name, value) for name, value in self._pairs if name not in changes]
        for name, value in changes.items():
            if value is None or value == "":
                continue
            if isinstance(value, list | tuple):
                pairs.extend((name, str(item)) for item in value)
            else:
                pairs.append((name, str(value)))
        return urlencode(pairs)


def split_url(value: str) -> tuple[str, str, str]:
    """`(path, query without "?", hash without "#")`."""
    parts = urlsplit(value)
    return parts.path or "/", parts.query, parts.fragment


class Location:
    """The current URL, read reactively; returned by [`use_location`][wybthon.router.use_location].

    Every property is a tracked read, so a binding or memo that reads one
    updates when the URL changes.
    """

    __slots__ = ()

    @property
    def path(self) -> str:
        """The path, such as `/users/42`."""
        return split_url(url())[0]

    @property
    def search(self) -> str:
        """The query string, with its leading `?` (or `""`)."""
        query = split_url(url())[1]
        return "?" + query if query else ""

    @property
    def hash(self) -> str:
        """The decoded fragment, without its leading `#`."""
        return unquote_plus(split_url(url())[2])

    @property
    def query(self) -> SearchParams:
        """The parsed query string."""
        return SearchParams(split_url(url())[1])

    @property
    def href(self) -> str:
        """Path, query, and hash together."""
        return url()

    def __repr__(self) -> str:
        return f"Location({url.peek()!r})"


_LOCATION = Location()


def use_location() -> Location:
    """The current URL; read `location.path`, `.search`, `.hash`, or `.query` reactively."""
    return _LOCATION
