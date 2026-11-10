"""`query` and `revalidate`: deduplicated, revalidating data reads, as in Solid Router 2.0."""

from __future__ import annotations

import asyncio
import inspect
import time
from collections.abc import Awaitable, Callable, Coroutine, Iterable
from typing import Any, overload

from .. import _wire
from ..reactivity import _core
from ..reactivity._core import Signal
from ..request import get_request_event
from ..server_functions import Redirect, Reload, Respond, ServerFunction, _redirect_render, _remote

__all__ = ["Query", "query", "revalidate"]

# How long a settled result is reused in the browser, so a link's preload and
# the page it opens share one fetch.
CACHE_SECONDS = 5.0


class _Entry:
    __slots__ = ("future", "settled")

    def __init__(self, future: asyncio.Future[Any]) -> None:
        self.future = future
        self.settled: float | None = None


# Browser-side cache and the version signal each cached key's readers track.
_entries: dict[str, _Entry] = {}
_versions: dict[str, Signal[int]] = {}


def _version(full: str) -> Signal[int]:
    signal = _versions.get(full)
    if signal is None:

        def unobserved() -> None:
            if _versions.get(full) is signal:
                del _versions[full]

        signal = _versions[full] = Signal(0, unobserved=unobserved, name=f"query {full}")
    return signal


class Query[**P, R]:
    """A deduplicated, revalidating read; returned by [`query`][wybthon.router.query].

    Call it like the function it wraps; the call returns a coroutine for
    the result. Read it in an async memo
    (`create_memo(lambda: get_user(props.params["id"]))`) and the memo
    loads under the nearest [`Loading`][wybthon.Loading] boundary,
    refetches when [`revalidate`][wybthon.router.revalidate] names its
    key, and holds the old value on screen while it does.

    Attributes:
        key: The key [`revalidate`][wybthon.router.revalidate] matches.
            A call's full key is this key followed by its arguments.
    """

    def __init__(self, fn: Callable[P, Awaitable[R]], key: str) -> None:
        self._fn = fn
        self.key = key
        self.__name__ = getattr(fn, "__name__", "query")
        self.__qualname__ = getattr(fn, "__qualname__", self.__name__)
        self.__module__ = getattr(fn, "__module__", __name__)
        self.__doc__ = getattr(fn, "__doc__", None)
        self.__wrapped__ = fn
        if isinstance(fn, ServerFunction):
            # A query is a read: the server function is called with GET.
            fn.method = "GET"

    def key_for(self, *args: P.args, **kwargs: P.kwargs) -> str:
        """The full key of a call with these arguments."""
        payload = [list(args), kwargs] if kwargs else list(args)
        return self.key + _wire.dumps(payload)

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> Coroutine[Any, Any, R]:
        full = self.key_for(*args, **kwargs)
        if _core._server_depth or get_request_event() is not None:
            event = get_request_event()
            cache: dict[str, asyncio.Future[Any]] | None = (
                event.locals.setdefault("__wyb_queries", {}) if event is not None else None
            )
            return self._server(full, args, kwargs, cache)
        # Reading the version subscribes the caller, so `revalidate` re-runs it.
        # A call outside a tracking scope has nothing to re-run, and a signal
        # nothing ever observes would never be released.
        if _core._current_observer is not None:
            _version(full)()
        return self._browser(full, args, kwargs)

    async def _invoke(self, args: tuple[Any, ...], kwargs: dict[str, Any]) -> R:
        fn = self._fn
        if isinstance(fn, ServerFunction):
            if _remote():
                return await fn._call_remote(args, kwargs, "GET")
            return await fn._call_local(args, kwargs)
        result: Any
        try:
            result = fn(*args, **kwargs)
            if inspect.isawaitable(result):
                result = await result
        except Redirect as response:
            result = response
        if isinstance(result, Redirect):
            await _follow(result)
        if isinstance(result, Respond):
            return result.value
        if isinstance(result, Reload):
            return None
        return result

    async def _server(
        self, full: str, args: tuple[Any, ...], kwargs: dict[str, Any], cache: dict[str, asyncio.Future[Any]] | None
    ) -> R:
        # Deduplicated for the lifetime of the request.
        if cache is None:
            return await self._invoke(args, kwargs)
        future = cache.get(full)
        if future is None:
            future = cache[full] = asyncio.ensure_future(self._invoke(args, kwargs))
        return await asyncio.shield(future)

    async def _browser(self, full: str, args: tuple[Any, ...], kwargs: dict[str, Any]) -> R:
        entry = _entries.get(full)
        now = time.monotonic()
        if entry is not None and entry.settled is not None and now - entry.settled > CACHE_SECONDS:
            entry = None
        if entry is None:
            future = asyncio.ensure_future(self._invoke(args, kwargs))
            entry = _entries[full] = _Entry(future)

            def settled(done: asyncio.Future[Any], entry: _Entry = entry) -> None:
                if done.cancelled() or done.exception() is not None:
                    # Failures aren't cached: the next read tries again.
                    if _entries.get(full) is entry:
                        del _entries[full]
                else:
                    entry.settled = time.monotonic()
                if len(_entries) > 256:
                    _prune()

            future.add_done_callback(settled)
        return await asyncio.shield(entry.future)

    def __repr__(self) -> str:
        return f"Query({self.key})"


async def _follow(response: Redirect) -> None:
    """What a redirect a query raised does: the page's response on the server, a navigation in the browser."""
    if _core._server_depth or get_request_event() is not None:
        _redirect_render(response)
        raise response
    from .. import server_functions

    server_functions._revalidate_hook(response.revalidate)
    server_functions._navigate_hook(response.url, True)
    # The read stays pending: the page it belongs to is leaving.
    await asyncio.get_running_loop().create_future()


def _prune() -> None:
    now = time.monotonic()
    for full, entry in list(_entries.items()):
        if entry.settled is not None and now - entry.settled > CACHE_SECONDS:
            del _entries[full]


@overload
def query[**P, R](fn: Callable[P, Awaitable[R]], key: str | None = None, /) -> Query[P, R]: ...


@overload
def query[**P, R](key: str, /) -> Callable[[Callable[P, Awaitable[R]]], Query[P, R]]: ...


def query(fn: Any, key: str | None = None, /) -> Any:
    """Wrap an async read so calls are deduplicated and can be revalidated by key.

    Use it as a decorator, bare or with a key, or call it with a function
    and a key, as in Solid:

    ```python
    @query
    @server_function
    async def get_user(user_id: int) -> User:
        return await db.users.get(user_id)


    @component
    def Profile(params: dict[str, str]):
        user = create_memo(lambda: get_user(int(params["id"])))
        return html(t"<h1>{user().name}</h1>")
    ```

    A query:

    1. dedupes calls on the server for the lifetime of the request;
    2. in the browser, reuses a result for five seconds after it arrives,
       so a link's preload and the page it opens share one fetch;
    3. refetches, in every memo that read it, when
       [`revalidate`][wybthon.router.revalidate] names its key, or when a
       mutation completes (see [`server_function`][wybthon.server_function]).

    A server function wrapped in a query is called with GET.

    Args:
        fn: The async function to wrap (or, used as `@query("key")`,
            the key).
        key: The query's key. Defaults to the server function's id, or
            the function's module and qualified name.
    """
    if isinstance(fn, str):
        name = fn
        return lambda inner: Query(inner, name)
    if key is None:
        key = fn.id if isinstance(fn, ServerFunction) else f"{fn.__module__}.{fn.__qualname__}"
    return Query(fn, key)


def revalidate(keys: str | Query[..., Any] | Iterable[str | Query[..., Any]] | None = None) -> None:
    """Refetch the queries whose keys start with `keys` (every query when omitted).

    Each memo that read a matching query runs again; a memo with a value
    holds it on screen until the new one lands. On the server it does
    nothing.

    Args:
        keys: A key, a [`Query`][wybthon.router.Query], or several. A key
            matches every call whose full key starts with it, so
            `revalidate(get_user)` refetches every user.
    """
    if _core._server_depth or get_request_event() is not None:
        return
    if keys is None:
        prefixes: list[str] | None = None
    elif isinstance(keys, str | Query):
        prefixes = [keys.key if isinstance(keys, Query) else keys]
    else:
        prefixes = [key.key if isinstance(key, Query) else str(key) for key in keys]
    if prefixes is not None and not prefixes:
        return

    def matches(full: str) -> bool:
        return prefixes is None or any(full.startswith(prefix) for prefix in prefixes)

    for full in [full for full in _entries if matches(full)]:
        del _entries[full]
    for full, signal in list(_versions.items()):
        if matches(full):
            signal._write(signal._latest() + 1)
    _core._schedule_flush()


def _apply_revalidation(keys: list[str] | None) -> None:
    """What a mutation's response asks the browser to refetch."""
    revalidate(keys)
