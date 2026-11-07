"""Server functions: Python that runs on the server, called from the browser like any `async def`.

Decorate a module-level `async def` with
[`server_function`][wybthon.server_function], and calling it from a
component sends its arguments to the server, runs it there, and returns
its result, as Solid 2.0's `"use server"` does:

```python
from dataclasses import dataclass

from wybthon import server_function


@dataclass
class Todo:
    id: int
    title: str


@server_function
async def list_todos(done: bool = False) -> list[Todo]:
    from app.server.db import database  # never imported in the browser

    return [Todo(*row) for row in database().execute("select id, title from todos where done = ?", [done])]
```

- **On the server** (while a page renders, or in another server
  function), the call runs the function directly.
- **In the browser**, the build has removed the function's body and every
  import only that body used, so neither reaches the page. The call
  posts its arguments to `{base}_wyb/fn/{module}:{name}` and awaits the
  answer. Arguments and results cross in Wybthon's wire format
  (`wybthon._wire`): JSON plus dataclasses, enums, tuples, sets, dates,
  `Decimal`, `UUID`, and bytes. On the server, every argument is
  rebuilt and validated from the function's own annotations, so a client
  can't send anything the function didn't declare; a mismatch is a 400.
- **Errors.** An exception the function raises arrives in the browser as
  [`ServerError`][wybthon.ServerError] with the exception's type name.
  Its message is sent in development, and in production only for a
  `ServerError` the function raised itself, so internals don't leak.
- **Responses.** Raise or return [`redirect`][wybthon.redirect],
  [`reload`][wybthon.reload], or [`respond`][wybthon.respond] to
  navigate, revalidate queries, or set the status and headers.
- **Mutations revalidate.** A POST call (the default) is treated as a
  mutation: when it completes, the browser revalidates every
  [`query`][wybthon.router.query] on the page, unless the function
  named what it changed with `respond(value, revalidate=[...])`.
  `@server_function(method="GET")` declares a read, which revalidates
  nothing; a server function wrapped in `query` is a GET automatically.
- **The request.** [`get_request_event`][wybthon.get_request_event]
  returns the request the call came in with, so a server function can
  read cookies and headers and call
  [`set_cookie`][wybthon.set_cookie] or
  [`http_header`][wybthon.http_header].

Server functions need a server: a project with `server = true` in its
`wybthon.toml`, served by `wyb dev`, `wyb serve`, or
[`wybthon.asgi`][wybthon.asgi] under any ASGI server.
"""

from __future__ import annotations

import asyncio
import inspect
import sys
import traceback
from collections.abc import Awaitable, Callable, Coroutine
from contextlib import contextmanager
from typing import Any, Literal, overload
from urllib.parse import parse_qs, quote, unquote

from . import _wire
from ._formdata import FormData
from ._warnings import is_dev_mode, log_error
from .reactivity._session import ServerError
from .request import RequestEvent, _current, get_request_event

__all__ = [
    "ServerFunction",
    "server_function",
    "redirect",
    "reload",
    "respond",
    "Redirect",
    "Reload",
    "Respond",
    "ServerResponse",
    "set_transport",
    "FN_PATH",
]

FN_PATH = "_wyb/fn/"
"""Where server functions are served, under the app's base path."""

Method = Literal["GET", "POST"]

# Every server function defined in this process, by id (server side).
_registry: dict[str, ServerFunction[..., Any]] = {}


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------


class ServerResponse(Exception):
    """Base of the responses a server function may raise or return."""

    revalidate: list[str] | None
    headers: dict[str, str]

    def __init__(self) -> None:
        super().__init__()
        self.revalidate = None
        self.headers = {}


class Redirect(ServerResponse):
    """Navigate to `url` (see [`redirect`][wybthon.redirect])."""

    def __init__(self, url: str, status: int, revalidate: list[str] | None, headers: dict[str, str] | None) -> None:
        super().__init__()
        if status not in (301, 302, 303, 307, 308):
            raise ValueError(f"A redirect needs a redirect status, not {status}")
        self.url = url
        self.status = status
        self.revalidate = revalidate
        self.headers = dict(headers or {})

    def __str__(self) -> str:
        return f"redirect to {self.url}"


class Reload(ServerResponse):
    """Revalidate queries without navigating (see [`reload`][wybthon.reload])."""

    def __init__(self, revalidate: list[str] | None, headers: dict[str, str] | None) -> None:
        super().__init__()
        self.revalidate = revalidate
        self.headers = dict(headers or {})


class Respond(ServerResponse):
    """A result with a status, headers, or revalidation keys (see [`respond`][wybthon.respond])."""

    def __init__(self, value: Any, status: int, revalidate: list[str] | None, headers: dict[str, str] | None) -> None:
        super().__init__()
        self.value = value
        self.status = status
        self.revalidate = revalidate
        self.headers = dict(headers or {})


def _keys(revalidate: str | list[str] | tuple[str, ...] | None) -> list[str] | None:
    if revalidate is None:
        return None
    if isinstance(revalidate, str):
        return [revalidate] if revalidate else []
    return [str(key) for key in revalidate]


def redirect(
    url: str,
    status: int = 302,
    *,
    revalidate: str | list[str] | None = None,
    headers: dict[str, str] | None = None,
) -> Redirect:
    """A redirect, for a server function, query, or form action to raise or return.

    In the browser, the router navigates to `url` (replacing the history
    entry); a JavaScript-free form post gets a `303` to it. Raised from a
    query while a page renders on the server, it becomes the page's
    response. `revalidate` names the queries to refetch first; by default
    a redirect from a mutation revalidates everything the next page reads.

    ```python
    @form_action
    @server_function
    async def log_in(form: FormData) -> None:
        user = await authenticate(form["email"], form["password"])
        set_cookie("session", user.session_token)
        raise redirect("/dashboard")
    ```
    """
    return Redirect(url, status, _keys(revalidate), headers)


def reload(*, revalidate: str | list[str] | None = None, headers: dict[str, str] | None = None) -> Reload:
    """Revalidate queries on the current page without navigating.

    `revalidate` names query keys (or key prefixes); omit it to
    revalidate every query on the page.
    """
    return Reload(_keys(revalidate), headers)


def respond(
    value: Any = None,
    *,
    status: int = 200,
    headers: dict[str, str] | None = None,
    revalidate: str | list[str] | None = None,
) -> Respond:
    """Return `value` with a status, headers, or the query keys this call changed.

    `revalidate=""` (or `[]`) marks a POST call that changed nothing, so
    the page's queries aren't refetched:

    ```python
    @server_function
    async def log_search(term: str) -> None:
        analytics.record(term)
        return respond(revalidate="")
    ```
    """
    return Respond(value, status, _keys(revalidate), headers)


# ---------------------------------------------------------------------------
# Hooks the router installs (the browser side of a response)
# ---------------------------------------------------------------------------


def _no_revalidate(keys: list[str] | None) -> None:
    pass


def _no_navigate(url: str, replace: bool) -> None:
    try:
        from js import window

        if replace:
            window.location.replace(url)
        else:
            window.location.assign(url)
    except ImportError:
        pass


_revalidate_hook: Callable[[list[str] | None], None] = _no_revalidate
_navigate_hook: Callable[[str, bool], None] = _no_navigate


def _set_hooks(revalidate: Callable[[list[str] | None], None], navigate: Callable[[str, bool], None]) -> None:
    global _revalidate_hook, _navigate_hook
    _revalidate_hook = revalidate
    _navigate_hook = navigate


# ---------------------------------------------------------------------------
# Transport (the browser side of a call)
# ---------------------------------------------------------------------------

# (method, url, headers, body) -> (status, headers, body)
Transport = Callable[[str, str, dict[str, str], Any], Awaitable[tuple[int, dict[str, str], bytes]]]


async def _fetch(method: str, url: str, headers: dict[str, str], body: Any) -> tuple[int, dict[str, str], bytes]:
    from pyodide.http import pyfetch

    options: dict[str, Any] = {"method": method, "headers": headers, "credentials": "same-origin"}
    if body is not None:
        options["body"] = body
    response = await pyfetch(url, **options)
    data = await response.bytes()
    names = {key.lower(): value for key, value in response.headers.items()}
    return response.status, names, data


_transport: Transport | None = None
_base = "/"


def set_transport(transport: Transport | None, *, base: str | None = None) -> None:
    """Send browser-side server function calls through `transport` (tests and tools).

    `wybthon.testing.serve` uses it to connect components rendered in
    CPython to an in-process ASGI app. With a transport set, calls are
    made remotely even outside a browser. `None` restores the default.
    """
    global _transport, _base
    _transport = transport
    if base is not None:
        _base = base.rstrip("/") + "/"


def _app_base() -> str:
    if _transport is not None:
        return _base
    try:
        from js import document

        element = document.getElementById("wyb-manifest")
        if element is not None:
            import json

            return str(json.loads(element.textContent).get("base", "/")).rstrip("/") + "/"
    except Exception:
        pass
    return _base


def _remote() -> bool:
    """Whether a call goes over the network: in the browser, or through a test transport."""
    if _transport is not None:
        return get_request_event() is None
    return sys.platform == "emscripten"


# ---------------------------------------------------------------------------
# ServerFunction
# ---------------------------------------------------------------------------


class ServerFunction[**P, R]:
    """A function that runs on the server; returned by [`server_function`][wybthon.server_function].

    Call it like the function it wraps: `await save(todo)`.

    Attributes:
        id: The function's id, `module:qualname`.
        method: `"POST"` (a mutation, the default) or `"GET"` (a read).
    """

    def __init__(self, fn: Callable[P, Awaitable[R]], method: Method) -> None:
        qualname = getattr(fn, "__qualname__", "")
        if not inspect.iscoroutinefunction(fn):
            raise TypeError(f"server_function needs an async def; {qualname} isn't one")
        if "<locals>" in qualname:
            raise TypeError(
                f"server_function needs a function defined at a module's top level (or in a class); {qualname} isn't"
            )
        self._fn = fn
        self.method: Method = method
        self.__name__ = fn.__name__
        self.__qualname__ = qualname
        self.__module__ = fn.__module__
        self.__doc__ = fn.__doc__
        self.__wrapped__ = fn
        self.id = f"{fn.__module__}:{qualname}"
        self._sig: Any = None
        _registry[self.id] = self

    @property
    def url(self) -> str:
        """The URL the browser calls, under the app's base path."""
        return _app_base() + FN_PATH + quote(self.id, safe=":")

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> Coroutine[Any, Any, R]:
        """Call the function: directly on the server, over HTTP in the browser."""
        if _remote():
            return self._call_remote(args, kwargs, self.method)
        return self._call_local(args, kwargs)

    async def _call_local(self, args: tuple[Any, ...], kwargs: dict[str, Any]) -> R:
        try:
            result = await self._fn(*args, **kwargs)
        except Redirect as response:
            _redirect_render(response)
            raise
        if isinstance(result, Redirect):
            _redirect_render(result)
            raise result
        if isinstance(result, Respond):
            return result.value
        if isinstance(result, Reload):
            return None
        return result

    async def _call_remote(self, args: tuple[Any, ...], kwargs: dict[str, Any], method: str, *, form: Any = None) -> R:
        transport = _transport or _fetch
        headers = {"x-wyb-fn": "1", "accept": "application/json"}
        url = self.url
        body: Any = None
        if form is not None:
            if args:
                url += "?args=" + quote(_wire.dumps(list(args)))
            if isinstance(form, FormData):
                content_type, body = form.encode()
                headers["content-type"] = content_type
            else:
                body = form  # a browser FormData; fetch sets its content type
        elif method == "GET":
            payload: dict[str, Any] = {"args": list(args)}
            if kwargs:
                payload["kwargs"] = kwargs
            url += "?args=" + quote(_wire.dumps(payload))
        else:
            headers["content-type"] = "application/json"
            body = _wire.dumps({"args": list(args), "kwargs": kwargs}).encode()
        status, _response_headers, data = await transport(method, url, headers, body)
        try:
            reply = _wire.loads(data) if data else {}
        except _wire.WireError:
            reply = None
        if not isinstance(reply, dict):
            raise ServerError(f"The server answered {status} to {self.id}", "ServerError")
        keys = reply.get("revalidate", _MISSING)
        if "error" in reply:
            error = reply["error"] or {}
            if method == "POST" and keys is not _MISSING:
                _revalidate_hook(keys)
            raise ServerError(str(error.get("message", "")), str(error.get("type", "Exception")))
        if "redirect" in reply:
            _revalidate_hook(None if keys is _MISSING else keys)
            _navigate_hook(str(reply["redirect"]), True)
            if method == "GET":
                # A read stays pending: the page it belongs to is leaving.
                await asyncio.get_running_loop().create_future()
            # A mutation completes, so the action around it settles and reveals
            # the navigation it held.
            return None
        if method == "POST":
            _revalidate_hook(None if keys is _MISSING else keys)
        return reply.get("ok")

    def __repr__(self) -> str:
        return f"ServerFunction({self.id}, {self.method})"

    def __get__(self, instance: Any, owner: Any = None) -> Any:
        return self


_MISSING: Any = object()


def _redirect_render(response: Redirect) -> None:
    """A redirect raised while a page renders on the server becomes the page's response."""
    event = get_request_event()
    if event is None:
        return
    head = event.response
    if not head.committed:
        head.status = response.status
        head.headers["location"] = [response.url]
        event.locals["__wyb_redirect"] = response.url
    else:
        event.locals.setdefault("__wyb_late_redirect", response.url)


@overload
def server_function[**P, R](fn: Callable[P, Awaitable[R]], /) -> ServerFunction[P, R]: ...


@overload
def server_function[**P, R](
    *, method: Method = "POST"
) -> Callable[[Callable[P, Awaitable[R]]], ServerFunction[P, R]]: ...


def server_function(fn: Any = None, /, *, method: Method = "POST") -> Any:
    """Make an `async def` run on the server, wherever it's called from.

    Use it bare (`@server_function`) for a mutation, called with POST, or
    with `method="GET"` for a read. See
    [`wybthon.server_functions`][wybthon.server_functions] for the whole
    contract.

    Args:
        fn: The `async def` to run on the server. It must be defined at
            a module's top level, so the browser and the server name it
            the same way.
        method: `"POST"` (the default; a mutation that revalidates the
            page's queries when it completes) or `"GET"` (a read).

    Returns:
        A [`ServerFunction`][wybthon.ServerFunction] with the same
        signature.
    """
    if method not in ("GET", "POST"):
        raise ValueError("method must be 'GET' or 'POST'")
    if fn is None:
        return lambda inner: ServerFunction(inner, method)
    return ServerFunction(fn, method)


# ---------------------------------------------------------------------------
# The server side of a call
# ---------------------------------------------------------------------------


class _BadRequest(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


def _bind(fn: ServerFunction[..., Any], args: list[Any], kwargs: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    """Rebuild and validate untrusted arguments from the function's annotations."""
    if fn._sig is None:
        fn._sig = _wire.parameters(fn._fn)
    params, _ = fn._sig
    built_args: list[Any] = []
    positional = [
        param
        for param in params
        if param[2] in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    ]
    variadic = next((param for param in params if param[2] is inspect.Parameter.VAR_POSITIONAL), None)
    named = {
        param[0]: param
        for param in params
        if param[2] in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
    }
    var_keyword = next((param for param in params if param[2] is inspect.Parameter.VAR_KEYWORD), None)
    for index, value in enumerate(args):
        if index < len(positional):
            name, annotation, _kind = positional[index]
        elif variadic is not None:
            name, annotation, _kind = variadic
        else:
            raise _BadRequest(400, f"{fn.id} takes {len(positional)} positional arguments")
        built_args.append(_wire.coerce(value, annotation, name))
    built_kwargs: dict[str, Any] = {}
    for name, value in kwargs.items():
        if not isinstance(name, str):
            raise _BadRequest(400, "Argument names must be strings")
        param = named.get(name)
        if param is None:
            if var_keyword is None:
                raise _BadRequest(400, f"{fn.id} has no parameter {name!r}")
            param = var_keyword
        built_kwargs[name] = _wire.coerce(value, param[1], name)
    try:
        inspect.signature(fn._fn).bind(*built_args, **built_kwargs)
    except TypeError as exc:
        raise _BadRequest(400, str(exc)) from exc
    return built_args, built_kwargs


def _same_origin(headers: dict[str, str]) -> bool:
    """Whether a request a page could have sent without our header came from our own pages."""
    site = headers.get("sec-fetch-site")
    if site is not None:
        return site in ("same-origin", "none")
    origin = headers.get("origin")
    if origin is None or origin == "null":
        return origin is None
    host = headers.get("host", "")
    return origin.split("://", 1)[-1] == host


async def handle(
    event: RequestEvent, fn_id: str, method: str, query: str, headers: dict[str, str], body: bytes
) -> tuple[int, dict[str, str], bytes, ServerFunction[..., Any] | None, Any]:
    """Run a server function for an HTTP request.

    Returns `(status, headers, body, function, outcome)`. `outcome` is
    the raw result or exception, for the caller's form-post handling.
    """
    fn = _registry.get(unquote(fn_id))
    if fn is None:
        return (
            404,
            {"content-type": "application/json"},
            b'{"error":{"type":"NotFound","message":"No such server function"}}',
            None,
            None,
        )
    called_by_script = headers.get("x-wyb-fn") == "1"
    content_type = headers.get("content-type", "")
    is_form = content_type.split(";", 1)[0].strip().lower() in (
        "application/x-www-form-urlencoded",
        "multipart/form-data",
    )
    outcome: Any = None
    try:
        if method not in ("GET", "POST"):
            raise _BadRequest(405, "Server functions accept GET and POST")
        if method != fn.method and not (method == "POST" and is_form):
            raise _BadRequest(405, f"{fn.id} is called with {fn.method}")
        if not called_by_script and not (is_form and _same_origin(headers)):
            raise _BadRequest(403, "Cross-site server function calls aren't allowed")
        params = parse_qs(query)
        raw_args = params.get("args", [None])[0]
        try:
            if is_form:
                args = _wire.loads(raw_args, trusted=False) if raw_args else []
                if not isinstance(args, list):
                    raise _BadRequest(400, "Bound arguments must be a list")
                args = [*args, FormData.parse(content_type, body)]
                kwargs: dict[str, Any] = {}
            else:
                text = raw_args if method == "GET" else body.decode("utf-8") if body else "{}"
                payload = _wire.loads(text or "{}", trusted=False)
                if not isinstance(payload, dict):
                    raise _BadRequest(400, "Malformed call")
                args = payload.get("args") or []
                kwargs = payload.get("kwargs") or {}
                if not isinstance(args, list) or not isinstance(kwargs, dict):
                    raise _BadRequest(400, "Malformed call")
            bound_args, bound_kwargs = _bind(fn, args, kwargs)
        except _wire.WireError as exc:
            raise _BadRequest(400, str(exc)) from exc
        except ValueError as exc:
            raise _BadRequest(400, str(exc)) from exc
        token = _current.set(event)
        try:
            outcome = await fn._fn(*bound_args, **bound_kwargs)
        except ServerResponse as response:
            outcome = response
        finally:
            _current.reset(token)
    except _BadRequest as exc:
        return exc.status, {"content-type": "application/json"}, _error_body("BadRequest", str(exc)), fn, exc
    except Exception as exc:
        outcome = exc
        if not isinstance(exc, ServerError):
            log_error(f"Server function {fn.id} raised: {exc}", exc)
        expose = is_dev_mode() or isinstance(exc, ServerError)
        type_name = exc.type_name if isinstance(exc, ServerError) else type(exc).__name__
        message = str(exc) if expose else "The server couldn't complete the request"
        reply: dict[str, Any] = {"error": {"type": type_name, "message": message}}
        if is_dev_mode() and not isinstance(exc, ServerError):
            reply["error"]["traceback"] = "".join(traceback.format_exception(exc))
        return 500, {"content-type": "application/json"}, _wire.dumps(reply).encode(), fn, outcome
    response_headers = {"content-type": "application/json", "cache-control": "no-store"}
    status = 200
    reply = {}
    if isinstance(outcome, Redirect):
        reply = {"redirect": outcome.url}
        response_headers.update(outcome.headers)
    elif isinstance(outcome, Reload):
        response_headers.update(outcome.headers)
    elif isinstance(outcome, Respond):
        reply = {"ok": outcome.value}
        status = outcome.status
        response_headers.update(outcome.headers)
    else:
        reply = {"ok": outcome}
    if isinstance(outcome, ServerResponse) and outcome.revalidate is not None:
        reply["revalidate"] = outcome.revalidate
    try:
        data = _wire.dumps(reply).encode()
    except _wire.WireError as exc:
        log_error(f"Server function {fn.id} returned a value that can't be sent: {exc}", exc)
        return 500, {"content-type": "application/json"}, _error_body("ServerError", str(exc)), fn, exc
    return status, response_headers, data, fn, outcome


def _error_body(type_name: str, message: str) -> bytes:
    return _wire.dumps({"error": {"type": type_name, "message": message}}).encode()


@contextmanager
def _remote_calls(transport: Transport, base: str = "/") -> Any:
    """Make calls in this block go through `transport` (tests)."""
    previous, previous_base = _transport, _base
    set_transport(transport, base=base)
    try:
        yield
    finally:
        set_transport(previous, base=previous_base)
