"""The small built-in HTTP server for ASGI apps (`wyb serve`, `wyb dev`)."""

from __future__ import annotations

import asyncio
import http.client
from typing import Any

from wybthon._http import start


async def app(scope: dict[str, Any], receive: Any, send: Any) -> None:
    message = await receive()
    body = message.get("body", b"")
    if scope["path"] == "/stream":
        await send({"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"text/plain")]})
        for part in (b"one ", b"two ", b"three"):
            await send({"type": "http.response.body", "body": part, "more_body": True})
        await send({"type": "http.response.body", "body": b"", "more_body": False})
        return
    if scope["path"] == "/boom":
        raise RuntimeError("boom")
    text = f"{scope['method']} {scope['path']}?{scope['query_string'].decode()} {body.decode()}".encode()
    await send(
        {"type": "http.response.start", "status": 201, "headers": [(b"content-length", str(len(text)).encode())]}
    )
    await send({"type": "http.response.body", "body": text})


def test_requests_keep_alive_stream_and_fail_safely():
    async def main() -> None:
        server = await start(app, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]

        def talk() -> list[tuple[int, bytes, str | None]]:
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            results = []
            connection.request("POST", "/echo?x=1", body=b"hello", headers={"content-type": "text/plain"})
            response = connection.getresponse()
            results.append((response.status, response.read(), response.getheader("transfer-encoding")))
            connection.request("GET", "/stream")
            response = connection.getresponse()
            results.append((response.status, response.read(), response.getheader("transfer-encoding")))
            connection.request("HEAD", "/echo")
            response = connection.getresponse()
            results.append((response.status, response.read(), None))
            connection.close()
            failing = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            failing.request("GET", "/boom")
            response = failing.getresponse()
            results.append((response.status, response.read(), None))
            return results

        try:
            results = await asyncio.to_thread(talk)
        finally:
            server.close()
            await server.wait_closed()
        assert results[0] == (201, b"POST /echo?x=1 hello", None)
        assert results[1] == (200, b"one two three", "chunked")
        assert results[2][0] == 201 and results[2][1] == b""
        assert results[3][0] == 500

    asyncio.run(main())
