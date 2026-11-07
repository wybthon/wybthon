"""Serve a Wybthon app from Python: pages rendered per request, server functions, and assets.

[`create_app`][wybthon.asgi.create_app] returns an ASGI application for a
project built with `server = true` in its `wybthon.toml`. It:

- **renders pages** on every request, streaming each
  [`Loading`][wybthon.Loading] boundary's content as its data arrives,
  into the build's page shell, which then boots Pyodide and hydrates;
- **runs server functions** posted (or, for queries, fetched) to
  `{base}_wyb/fn/{id}`, including JavaScript-free form posts, which it
  answers with a redirect back and a flash cookie carrying the result;
- **serves HTTP handlers** (`GET`, `POST`, ...) that file route modules
  define, for API endpoints;
- **serves the build's assets** with long-lived caching for the
  content-hashed ones.

Run it with `wyb serve` (or `wyb dev` while developing), or under any
ASGI server:

```bash
WYBTHON_PROJECT=. uvicorn --factory wybthon.asgi:create_app
```

**Middleware.** List `module:function` names under `middleware` in
`wybthon.toml`; each is `async def handle(event, call_next)` and returns
`await call_next()` or a [`Response`][wybthon.asgi.Response] of its
own. Set `event.locals` (the signed-in user, a database session) for
components and server functions to read through
[`get_request_event`][wybthon.get_request_event].
"""

from __future__ import annotations

import asyncio
import dataclasses
import datetime
import importlib
import inspect
import json
import mimetypes
import os
import re
import sys
import tomllib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote, urlsplit

from . import _split, server_functions
from ._formdata import FormData
from ._warnings import log_error, set_dev_mode
from .reactivity import _core
from .request import RequestEvent, _current

__all__ = ["App", "Request", "Response", "create_app"]

_APP_START = "<!-- wyb:app -->"
_APP_END = "<!-- /wyb:app -->"
_IMMUTABLE = re.compile(r"^assets/[^/]+\.[a-f0-9]{16}\.(js|zip)$")


@dataclass
class Response:
    """An HTTP response from middleware or an HTTP handler.

    Attributes:
        body: The body; a `str` is sent as UTF-8.
        status: The status code.
        headers: Header values by name.
        cookies: `set-cookie` values, one per cookie.
    """

    body: bytes | str = b""
    status: int = 200
    headers: dict[str, str] = field(default_factory=dict)
    cookies: list[str] = field(default_factory=list)
    stream: Any = field(default=None, repr=False)
    """More of the body, sent after `body` as it arrives: an async iterator of `str` or `bytes`."""

    def encoded(self) -> bytes:
        """The body as bytes."""
        return self.body.encode("utf-8") if isinstance(self.body, str) else self.body


class Request:
    """The HTTP request, as `event.request` for pages, server functions, and handlers.

    Attributes:
        method: The HTTP method.
        path: The URL path.
        query: The query string, without `?`.
        headers: Header values by lowercase name.
        body: The request body.
        scope: The raw ASGI scope.
    """

    __slots__ = ("method", "path", "query", "headers", "body", "scope")

    def __init__(self, scope: dict[str, Any], body: bytes) -> None:
        self.scope = scope
        self.method: str = scope.get("method", "GET")
        self.path: str = scope.get("path", "/")
        raw_query = scope.get("query_string", b"")
        self.query: str = raw_query.decode("latin-1") if isinstance(raw_query, bytes) else str(raw_query)
        self.headers: dict[str, str] = {}
        for name, value in scope.get("headers", []):
            key = name.decode("latin-1").lower()
            text = value.decode("latin-1")
            self.headers[key] = f"{self.headers[key]}, {text}" if key in self.headers and key != "cookie" else text
        self.body = body

    @property
    def url(self) -> str:
        """Path and query."""
        return self.path + ("?" + self.query if self.query else "")

    def json(self) -> Any:
        """The body parsed as JSON."""
        return json.loads(self.body or b"null")

    def form(self) -> FormData:
        """The body parsed as a form."""
        return FormData.parse(self.headers.get("content-type", ""), self.body)

    def __repr__(self) -> str:
        return f"Request({self.method} {self.url})"


Middleware = Callable[[RequestEvent, Callable[[], Awaitable[Response]]], Awaitable[Response]]


def _plain(value: Any) -> Any:
    """JSON for an HTTP handler's result (plain JSON, not the wire format)."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return dataclasses.asdict(value)
    if isinstance(value, datetime.date | datetime.time):
        return value.isoformat()
    if isinstance(value, set | frozenset | tuple):
        return list(value)
    return str(value)


class App:
    """The ASGI application [`create_app`][wybthon.asgi.create_app] returns.

    Attributes:
        project: The project directory.
        dist: The build directory it serves.
        base: The app's base path, with a trailing slash.
        dev: Whether it's serving `wyb dev`.
    """

    def __init__(self, project: Path, dist: Path, *, dev: bool = False, max_body: int = 10 * 1024 * 1024) -> None:
        self.project = project
        self.dist = dist
        self.dev = dev
        self.max_body = max_body
        self.page_hook: Callable[[str], str] | None = None
        self.extra_routes: dict[str, Callable[[dict[str, Any], Any, Any], Awaitable[None]]] = {}
        self._loaded = False
        self.load()

    # -- loading -----------------------------------------------------------

    def load(self) -> None:
        """Read the build and import the application (again, after a rebuild)."""
        manifest_path = self.dist / "manifest.json"
        if not manifest_path.is_file():
            raise ValueError(f"{self.dist} isn't a Wybthon build; run `wyb build` first")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not manifest.get("server"):
            raise ValueError("The build isn't a server build: set server = true in wybthon.toml and build again")
        self.manifest = manifest
        self.base: str = manifest.get("base", "/")
        server_functions._base = self.base
        shell = (self.dist / "200.html").read_text(encoding="utf-8")
        if shell.count(_APP_START) != 1 or shell.count(_APP_END) != 1:
            raise ValueError(f"index.html needs one {_APP_START} ... {_APP_END} region to render pages into")
        start, end = shell.index(_APP_START), shell.index(_APP_END) + len(_APP_END)
        self._head, self._tail = shell[:start], shell[end:]
        self._prerendered = set(manifest.get("prerendered", []))
        config_path = self.project / "wybthon.toml"
        self.config = tomllib.loads(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}
        app_dir = self.config.get("app-dir", "app")
        if self._loaded:
            self._forget_modules(app_dir)
        project = str(self.project)
        if project not in sys.path:
            sys.path.insert(0, project)
        set_dev_mode(self.dev)
        module_name, export = manifest["entry"].split(":", 1)
        _core._server_depth += 1
        try:
            importlib.invalidate_caches()
            self.factory = getattr(importlib.import_module(module_name), export)
            self._import_server_modules(Path(self.project / app_dir))
            self.middleware: list[Middleware] = [_resolve(name) for name in self.config.get("middleware", [])]
            self.api = self._api_routes(app_dir)
            self._page_routes = self._file_routes(app_dir) if self.api else []
        finally:
            _core._server_depth -= 1
        self._loaded = True

    def _forget_modules(self, app_dir: str) -> None:
        package = app_dir.replace("/", ".")
        for name in [name for name in sys.modules if name == package or name.startswith(package + ".")]:
            del sys.modules[name]
        for key in [key for key, fn in server_functions._registry.items() if fn.__module__.startswith(package)]:
            del server_functions._registry[key]

    def _import_server_modules(self, app: Path) -> None:
        """Import every module that defines server functions, so calls find them."""
        routes = _routes_package(self.project, app, self.config)
        for path in sorted(app.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            source = path.read_text(encoding="utf-8")
            if "server_function" not in source or not _split.server_functions(source):
                continue
            relative = path.relative_to(self.project).with_suffix("").parts
            if routes is not None and path.is_relative_to(routes[1]):
                from .router._files import load_route_module

                load_route_module(routes[0], path.relative_to(routes[1]).with_suffix("").parts)
                continue
            parts = list(relative)
            if parts[-1] == "__init__":
                parts.pop()
            importlib.import_module(".".join(parts))

    def _file_routes(self, app_dir: str) -> list[Any]:
        routes = _routes_package(self.project, self.project / app_dir, self.config)
        if routes is None:
            return []
        from .router._files import file_routes

        return file_routes(routes[0])

    def _api_routes(self, app_dir: str) -> list[Any]:
        routes = _routes_package(self.project, self.project / app_dir, self.config)
        if routes is None:
            return []
        from .router._files import api_routes

        return api_routes(routes[0])

    # -- ASGI --------------------------------------------------------------

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        """The ASGI entry point."""
        if scope["type"] == "lifespan":
            while True:
                message = await receive()
                if message["type"] == "lifespan.startup":
                    await send({"type": "lifespan.startup.complete"})
                elif message["type"] == "lifespan.shutdown":
                    await send({"type": "lifespan.shutdown.complete"})
                    return
        if scope["type"] != "http":
            return
        extra = self.extra_routes.get(scope.get("path", ""))
        if extra is not None:
            await extra(scope, receive, send)
            return
        try:
            body = await self._body(receive)
        except _TooLarge:
            await _send(send, Response("Request body too large", 413, {"content-type": "text/plain"}))
            return
        request = Request(scope, body)
        await self.handle(request, send)

    async def _body(self, receive: Any) -> bytes:
        chunks: list[bytes] = []
        size = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                break
            chunk = message.get("body", b"")
            size += len(chunk)
            if size > self.max_body:
                raise _TooLarge
            chunks.append(chunk)
            if not message.get("more_body"):
                break
        return b"".join(chunks)

    async def handle(self, request: Request, send: Any) -> None:
        """Answer one request (the ASGI entry point, after reading its body)."""
        base = self.base.rstrip("/")
        path = request.path
        if base and path != base and not path.startswith(base + "/"):
            await _send(send, Response("Not found", 404, {"content-type": "text/plain"}))
            return
        relative = path[len(base) :].lstrip("/")
        event = RequestEvent(url=request.url, request=request, method=request.method, headers=request.headers)
        token = _current.set(event)
        try:
            if relative.startswith(server_functions.FN_PATH):
                await self._server_function(event, request, relative[len(server_functions.FN_PATH) :], send)
                return
            static = self._static(relative)
            if static is not None and request.method in ("GET", "HEAD"):
                await _send(send, static, head=request.method == "HEAD")
                return

            async def core() -> Response:
                return await self._dispatch(event, request, relative)

            response = await self._run_middleware(event, core)
            await _send(send, response, head=request.method == "HEAD")
        finally:
            _current.reset(token)

    async def _run_middleware(self, event: RequestEvent, core: Callable[[], Awaitable[Response]]) -> Response:
        handler = core
        for middleware in reversed(self.middleware):

            def wrap(
                inner: Callable[[], Awaitable[Response]], mw: Middleware = middleware
            ) -> Callable[[], Awaitable[Response]]:
                async def call() -> Response:
                    return await mw(event, inner)

                return call

            handler = wrap(handler)
        return await handler()

    async def _dispatch(self, event: RequestEvent, request: Request, relative: str) -> Response:
        pathname = "/" + relative
        api = self._api_match(pathname, request)
        if api is not None:
            return await self._api(event, request, *api)
        if request.method not in ("GET", "HEAD"):
            return Response("Method not allowed", 405, {"content-type": "text/plain", "allow": "GET, HEAD"})
        route = "/" + relative.strip("/") if relative.strip("/") else "/"
        if route in self._prerendered:
            page = self.dist / relative.strip("/") / "index.html" if relative.strip("/") else self.dist / "index.html"
            if page.is_file():
                return self._page_response(page.read_text(encoding="utf-8"), 200, {})
        return await self._render(event)

    # -- pages -------------------------------------------------------------

    def _page_response(self, html: str, status: int, headers: dict[str, list[str]]) -> Response:
        if self.page_hook is not None:
            html = self.page_hook(html)
        flat = {name: ", ".join(values) for name, values in headers.items() if name != "set-cookie"}
        flat.setdefault("content-type", "text/html; charset=utf-8")
        flat.setdefault("cache-control", "no-cache")
        return Response(html, status, flat, list(headers.get("set-cookie", [])))

    async def _render(self, event: RequestEvent) -> Response:
        """Render the page: wait for its shell, then stream the rest through the response."""
        from .server import render_to_stream

        view: Any = self.factory
        if inspect.iscoroutinefunction(view):
            view = await view()
        chunks: Any = render_to_stream(view, event=event).__aiter__()
        try:
            shell = await anext(chunks)
        except StopAsyncIteration:
            shell = ""
        except Exception as exc:
            log_error(f"Rendering {event.url} failed: {exc}", exc)
            return Response("Internal server error", 500, {"content-type": "text/plain"})
        redirect_to = event.locals.get("__wyb_redirect")
        if redirect_to:
            await chunks.aclose()
            return _redirect_response(event, str(redirect_to))
        hook = self.page_hook

        async def rest() -> Any:
            try:
                async for chunk in chunks:
                    yield chunk
            except ConnectionError:
                raise
            except Exception as exc:
                log_error(f"Rendering {event.url} failed: {exc}", exc)
            tail = self._tail
            yield hook(tail) if hook is not None else tail

        first = self._head + shell
        if hook is not None:
            first = hook(first)
        headers = {name: ", ".join(values) for name, values in event.response.headers.items() if name != "set-cookie"}
        headers.setdefault("content-type", "text/html; charset=utf-8")
        headers.setdefault("cache-control", "no-cache")
        cookies = list(event.response.headers.get("set-cookie", []))
        return Response(first, event.response.status, headers, cookies, stream=rest())

    def _headers(self, event: RequestEvent) -> list[tuple[str, str]]:
        headers = [(name, value) for name, value in event.response.header_items()]
        names = {name for name, _ in headers}
        if "content-type" not in names:
            headers.append(("content-type", "text/html; charset=utf-8"))
        if "cache-control" not in names:
            headers.append(("cache-control", "no-cache"))
        return headers

    # -- server functions ------------------------------------------------

    async def _server_function(self, event: RequestEvent, request: Request, fn_id: str, send: Any) -> None:
        async def core() -> Response:
            status, headers, body, fn, outcome = await server_functions.handle(
                event, fn_id, request.method, request.query, request.headers, request.body
            )
            native = request.headers.get("x-wyb-fn") != "1" and status != 403
            if native and fn is not None:
                return self._form_post_response(event, request, fn, status, outcome)
            return self._with_declared(event, Response(body, status, headers))

        response = await self._run_middleware(event, core)
        await _send(send, response)

    def _with_declared(self, event: RequestEvent, response: Response) -> Response:
        """Add the headers and cookies a server function declared."""
        cookies: list[str] = []
        for name, values in event.response.headers.items():
            if name == "set-cookie":
                cookies.extend(values)
            else:
                response.headers.setdefault(name, ", ".join(values))
        response.cookies.extend(cookies)
        return response

    def _form_post_response(
        self, event: RequestEvent, request: Request, fn: Any, status: int, outcome: Any
    ) -> Response:
        """Answer a JavaScript-free form post: a redirect, and the result in a flash cookie."""
        from .router._forms import FLASH_COOKIE, flash_cookie

        target: str | None = None
        if isinstance(outcome, server_functions.Redirect):
            target = outcome.url
        referer = request.headers.get("referer")
        if target is None and referer:
            parts = urlsplit(referer)
            if not parts.netloc or parts.netloc == request.headers.get("host"):
                target = parts.path + ("?" + parts.query if parts.query else "")
        target = target or self.base
        form = FormData()
        args: list[Any] = []
        try:
            form = request.form()
        except ValueError:
            pass
        error = (
            outcome
            if isinstance(outcome, BaseException) and not isinstance(outcome, server_functions.ServerResponse)
            else None
        )
        result = (
            outcome.value
            if isinstance(outcome, server_functions.Respond)
            else None
            if isinstance(outcome, BaseException)
            else outcome
        )
        from .router._forms import _by_path

        action = _by_path.get(server_functions.FN_PATH + quote(fn.id, safe=":"))
        name = action.name if action is not None else fn.id
        from urllib.parse import parse_qs

        raw = parse_qs(request.query).get("args", [None])[0]
        if raw:
            from . import _wire

            try:
                decoded = _wire.loads(raw, trusted=False)
                args = decoded if isinstance(decoded, list) else []
            except _wire.WireError:
                args = []
        value = flash_cookie(name, request.url, args, form, result, error)
        cookie = f"{FLASH_COOKIE}={value}; Path={self.base}; Max-Age=30; SameSite=Lax"
        response = Response(b"", 303, {"location": target})
        response = self._with_declared(event, response)
        response.cookies.append(cookie)
        return response

    # -- HTTP handlers -----------------------------------------------------

    def _api_match(self, pathname: str, request: Request) -> tuple[Any, dict[str, str]] | None:
        if not self.api:
            return None
        from .router._match import match_path

        method = "GET" if request.method == "HEAD" else request.method
        wants_page = method == "GET" and "text/html" in request.headers.get("accept", "")
        for route in self.api:
            if method not in route.methods:
                continue
            params = match_path(pathname, route.path)
            if params is None:
                continue
            if wants_page and self._has_page(pathname):
                return None
            return route, params
        return None

    def _has_page(self, pathname: str) -> bool:
        from .router._match import resolve

        return resolve(self._page_routes, pathname) is not None

    async def _api(self, event: RequestEvent, request: Request, route: Any, params: dict[str, str]) -> Response:
        method = "GET" if request.method == "HEAD" else request.method
        handler = route.handler(method)
        event.locals["params"] = params
        try:
            result = handler(event)
            if inspect.isawaitable(result):
                result = await result
        except server_functions.ServerResponse as response:
            result = response
        except Exception as exc:
            log_error(f"{method} {request.path} raised: {exc}", exc)
            return Response("Internal server error", 500, {"content-type": "text/plain"})
        return self._with_declared(event, _handler_response(result))

    # -- static files ------------------------------------------------------

    def _static(self, relative: str) -> Response | None:
        if not relative or "." not in relative.rsplit("/", 1)[-1]:
            return None
        parts = Path(unquote(relative)).parts
        if any(part.startswith(".") or part == ".." for part in parts) or relative.endswith(".html"):
            return None
        target = (self.dist / Path(*parts)).resolve()
        if not target.is_relative_to(self.dist.resolve()) or not target.is_file():
            return None
        kind = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if kind.startswith("text/") or kind in ("application/javascript", "application/json"):
            kind += "; charset=utf-8"
        immutable = bool(_IMMUTABLE.match(relative)) and not self.dev
        cache = "public, max-age=31536000, immutable" if immutable else "no-cache"
        return Response(target.read_bytes(), 200, {"content-type": kind, "cache-control": cache})


class _TooLarge(Exception):
    pass


def _handler_response(result: Any) -> Response:
    if isinstance(result, Response):
        return result
    if isinstance(result, server_functions.Redirect):
        return Response(b"", result.status, {"location": result.url, **result.headers})
    if isinstance(result, server_functions.Respond):
        body = json.dumps(result.value, default=_plain).encode() if result.value is not None else b""
        headers = {"content-type": "application/json", **result.headers} if body else dict(result.headers)
        return Response(body, result.status, headers)
    if isinstance(result, server_functions.Reload):
        return Response(b"", 204, dict(result.headers))
    if result is None:
        return Response(b"", 204, {})
    if isinstance(result, str):
        return Response(result, 200, {"content-type": "text/plain; charset=utf-8"})
    if isinstance(result, bytes):
        return Response(result, 200, {"content-type": "application/octet-stream"})
    return Response(json.dumps(result, default=_plain).encode(), 200, {"content-type": "application/json"})


def _redirect_response(event: RequestEvent, target: str) -> Response:
    headers = {name: ", ".join(values) for name, values in event.response.headers.items() if name != "set-cookie"}
    headers["location"] = target
    status = event.response.status if 300 <= event.response.status < 400 else 302
    return Response(b"", status, headers, list(event.response.headers.get("set-cookie", [])))


async def _start(send: Any, status: int, headers: list[tuple[str, str]]) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [(name.encode("latin-1"), value.encode("latin-1")) for name, value in headers],
        }
    )


async def _send(send: Any, response: Response, *, head: bool = False) -> None:
    body = response.encoded()
    headers = [(name.lower(), value) for name, value in response.headers.items()]
    headers += [("set-cookie", cookie) for cookie in response.cookies]
    stream = response.stream
    if stream is None and not any(name == "content-length" for name, _ in headers):
        headers.append(("content-length", str(len(body))))
    try:
        await _start(send, response.status, headers)
        if stream is None or head:
            await send({"type": "http.response.body", "body": b"" if head else body})
            if stream is not None:
                await stream.aclose()
            return
        await send({"type": "http.response.body", "body": body, "more_body": True})
        async for chunk in stream:
            data = chunk.encode("utf-8") if isinstance(chunk, str) else chunk
            await send({"type": "http.response.body", "body": data, "more_body": True})
        await send({"type": "http.response.body", "body": b"", "more_body": False})
    except ConnectionError:
        if stream is not None:
            await stream.aclose()


def _resolve(name: str) -> Any:
    module, _, attr = name.partition(":")
    if not attr:
        raise ValueError(f"middleware entries look like module:function, not {name!r}")
    return getattr(importlib.import_module(module), attr)


def _routes_package(project: Path, app: Path, config: dict[str, Any]) -> tuple[str, Path] | None:
    """The file routes package's dotted name and directory, when the project has one."""
    configured = config.get("routes")
    directory = (project / configured).resolve() if configured else (app / "routes").resolve()
    if not directory.is_dir():
        return None
    return ".".join(directory.relative_to(project.resolve()).parts), directory


def create_app(
    project: str | os.PathLike[str] | None = None, *, dist: str | os.PathLike[str] | None = None, dev: bool = False
) -> App:
    """The ASGI application for a Wybthon project built with `server = true`.

    Args:
        project: The project directory. Defaults to `$WYBTHON_PROJECT`,
            or the current directory.
        dist: The build to serve. Defaults to the project's `dist`.
        dev: Serve in development mode (dev diagnostics on, no
            long-lived caching). `wyb dev` sets it.

    Returns:
        An [`App`][wybthon.asgi.App].
    """
    root = Path(project or os.environ.get("WYBTHON_PROJECT", ".")).resolve()
    return App(root, Path(dist).resolve() if dist else root / "dist", dev=dev)


def run(app: App, *, host: str = "127.0.0.1", port: int = 8000) -> None:
    """Serve `app` with Wybthon's small built-in HTTP server (`wyb serve`)."""
    from ._http import serve

    asyncio.run(serve(app, host, port))
