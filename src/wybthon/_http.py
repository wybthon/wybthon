"""A small asyncio HTTP/1.1 server for ASGI apps (`wyb serve` and `wyb dev`).

It speaks enough HTTP for a Wybthon app: keep-alive, request bodies with
a `Content-Length`, chunked (streamed) responses, and `HEAD`. It isn't
meant to face the internet on its own; behind a reverse proxy, or for
production traffic, run [`wybthon.asgi`][wybthon.asgi] under an ASGI
server such as uvicorn.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import unquote

__all__ = ["serve", "start"]

ASGIApp = Callable[[dict[str, Any], Any, Any], Awaitable[None]]

_REASONS = {
    200: "OK",
    201: "Created",
    204: "No Content",
    301: "Moved Permanently",
    302: "Found",
    303: "See Other",
    304: "Not Modified",
    307: "Temporary Redirect",
    308: "Permanent Redirect",
    400: "Bad Request",
    403: "Forbidden",
    404: "Not Found",
    405: "Method Not Allowed",
    411: "Length Required",
    413: "Payload Too Large",
    500: "Internal Server Error",
}

_MAX_HEAD = 64 * 1024
MAX_BODY = 10 * 1024 * 1024
"""The largest request body the server reads, in bytes (`wybthon.asgi.App` applies the same limit)."""


class _Connection:
    def __init__(
        self,
        app: ASGIApp,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        server: tuple[str, int],
        max_body: int = MAX_BODY,
    ) -> None:
        self.app = app
        self.reader = reader
        self.writer = writer
        self.server = server
        self.max_body = max_body

    async def run(self) -> None:
        try:
            while await self.request():
                pass
        except ConnectionError, asyncio.IncompleteReadError, asyncio.LimitOverrunError:
            pass
        finally:
            try:
                self.writer.close()
                await self.writer.wait_closed()
            except Exception:
                pass

    async def request(self) -> bool:
        try:
            head = await self.reader.readuntil(b"\r\n\r\n")
        except asyncio.IncompleteReadError:
            return False
        if len(head) > _MAX_HEAD:
            await self.simple(431, b"Request header fields too large")
            return False
        lines = head.decode("latin-1").split("\r\n")
        try:
            method, target, version = lines[0].split(" ", 2)
        except ValueError:
            await self.simple(400, b"Bad request")
            return False
        headers: list[tuple[bytes, bytes]] = []
        lookup: dict[str, str] = {}
        for line in lines[1:]:
            if not line:
                continue
            name, _, value = line.partition(":")
            name, value = name.strip().lower(), value.strip()
            headers.append((name.encode("latin-1"), value.encode("latin-1")))
            lookup[name] = value
        if "chunked" in lookup.get("transfer-encoding", "").lower():
            await self.simple(411, b"Chunked request bodies aren't supported")
            return False
        raw_length = lookup.get("content-length", "0") or "0"
        if not raw_length.isdigit():
            await self.simple(400, b"Bad content-length")
            return False
        length = int(raw_length)
        if length > self.max_body:
            # Answered before reading it: a body this size is never buffered.
            await self.simple(413, b"Request body too large")
            return False
        body = await self.reader.readexactly(length) if length else b""
        path, _, query = target.partition("?")
        keep_alive = lookup.get("connection", "").lower() != "close" and version == "HTTP/1.1"
        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": version.removeprefix("HTTP/"),
            "method": method.upper(),
            "scheme": "http",
            "path": unquote(path),
            "raw_path": path.encode("latin-1"),
            "query_string": query.encode("latin-1"),
            "root_path": "",
            "headers": headers,
            "client": self.writer.get_extra_info("peername"),
            "server": self.server,
        }
        received = False

        async def receive() -> dict[str, Any]:
            nonlocal received
            if not received:
                received = True
                return {"type": "http.request", "body": body, "more_body": False}
            await asyncio.Event().wait()
            return {"type": "http.disconnect"}

        state: dict[str, Any] = {"started": False, "chunked": False, "done": False}

        async def send(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                status = int(message["status"])
                response_headers = [(bytes(name), bytes(value)) for name, value in message.get("headers", [])]
                names = {name.lower() for name, _ in response_headers}
                lines = [f"HTTP/1.1 {status} {_REASONS.get(status, 'Status')}".encode()]
                lines += [name + b": " + value for name, value in response_headers]
                if b"content-length" not in names and method.upper() != "HEAD" and status not in (204, 304):
                    lines.append(b"transfer-encoding: chunked")
                    state["chunked"] = True
                lines.append(b"connection: " + (b"keep-alive" if keep_alive else b"close"))
                self.writer.write(b"\r\n".join(lines) + b"\r\n\r\n")
                state["started"] = True
            elif message["type"] == "http.response.body":
                data = message.get("body", b"")
                more = message.get("more_body", False)
                if state["chunked"]:
                    if data:
                        self.writer.write(f"{len(data):x}\r\n".encode() + data + b"\r\n")
                    if not more:
                        self.writer.write(b"0\r\n\r\n")
                elif data and method.upper() != "HEAD":
                    self.writer.write(data)
                if not more:
                    state["done"] = True
                await self.writer.drain()

        try:
            await self.app(scope, receive, send)
        except ConnectionError:
            return False
        except Exception as exc:
            import traceback

            traceback.print_exception(exc)
            if not state["started"]:
                await self.simple(500, b"Internal server error")
                return False
        if not state["started"]:
            await self.simple(500, b"The application sent no response")
            return False
        if not state["done"]:
            return False
        return keep_alive

    async def simple(self, status: int, body: bytes) -> None:
        self.writer.write(
            f"HTTP/1.1 {status} {_REASONS.get(status, 'Status')}\r\ncontent-type: text/plain\r\n"
            f"content-length: {len(body)}\r\nconnection: close\r\n\r\n".encode()
            + body
        )
        await self.writer.drain()


async def start(app: ASGIApp, host: str, port: int, *, max_body: int = MAX_BODY) -> asyncio.Server:
    """Start serving `app`; returns the server (bound to `server.sockets[0]`)."""
    bound: tuple[str, int] = (host, port)

    async def connected(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await _Connection(app, reader, writer, bound, max_body).run()

    server = await asyncio.start_server(connected, host, port, limit=_MAX_HEAD)
    bound = server.sockets[0].getsockname()[:2]
    return server


async def serve(app: ASGIApp, host: str = "127.0.0.1", port: int = 8000, *, max_body: int = MAX_BODY) -> None:
    """Serve `app` until cancelled."""
    server = await start(app, host, port, max_body=max_body)
    address = server.sockets[0].getsockname()
    print(f"Serving at http://{address[0]}:{address[1]}/", flush=True)
    async with server:
        await server.serve_forever()
