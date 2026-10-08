"""The request being server-rendered, and the response head the render declares.

Components call [`http_status`][wybthon.http_status] and
[`http_header`][wybthon.http_header] to shape the HTTP response while
they render on the server, and
[`get_request_event`][wybthon.get_request_event] to read the request.
In the browser all three are harmless: there's no request, and the
response head was sent long ago.

```python
from wybthon import component, h1, http_status


@component
def NotFound():
    http_status(404)
    return h1("Not found")
```

On the server, pass a [`RequestEvent`][wybthon.RequestEvent] to the
render function and read its `response` afterward:

```python
from wybthon import RequestEvent
from wybthon.server import render_to_string

event = RequestEvent(url=request.path, request=request)
body = render_to_string(App(), event=event)
return Response(body, status=event.response.status, headers=event.response.header_items())
```

Declarations belong to the reactive scope that made them, as in
Solid 2.0: when that scope is disposed before the response is
committed (an error boundary recovering, a branch switching), the
previous status or header is restored. Once the head is committed (the
render finished, or a stream sent its shell), further declarations are
ignored.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .reactivity import _core

__all__ = ["RequestEvent", "ResponseHead", "get_request_event", "http_status", "http_header"]


@dataclass
class ResponseHead:
    """The status and headers a server render declares.

    Attributes:
        status: The HTTP status code.
        status_text: An optional reason phrase.
        headers: Header values by lowercase name, in declaration order.
        committed: Set once the head can no longer change (the render
            finished, or a stream sent its shell).
    """

    status: int = 200
    status_text: str | None = None
    headers: dict[str, list[str]] = field(default_factory=dict)
    committed: bool = False
    # Live declarations, oldest first. Retracting one removes only that
    # entry, and the head is recomputed from what survives, so the order in
    # which scopes are disposed doesn't matter.
    _statuses: list[tuple[object, int, str | None]] = field(default_factory=list, repr=False)
    _headers: list[tuple[object, str, str, bool]] = field(default_factory=list, repr=False)
    _base: tuple[int, str | None, dict[str, list[str]]] | None = field(default=None, repr=False)

    def header_items(self) -> list[tuple[str, str]]:
        """Return `(name, value)` pairs, one per value, for an HTTP response."""
        return [(name, value) for name, values in self.headers.items() for value in values]

    def _declare(self) -> None:
        if self._base is None:
            self._base = (self.status, self.status_text, {k: list(v) for k, v in self.headers.items()})

    def _recompute(self) -> None:
        assert self._base is not None
        status, text, headers = self._base
        headers = {k: list(v) for k, v in headers.items()}
        if self._statuses:
            _, status, text = self._statuses[-1]
        for _, name, value, append in self._headers:
            headers[name] = [*headers.get(name, []), value] if append else [value]
        self.status, self.status_text, self.headers = status, text, headers


@dataclass
class RequestEvent:
    """One request being rendered on the server.

    Attributes:
        url: The request path and query, read by the router.
        request: The framework's request object, passed through as is.
        locals: Per-request values for the application (the signed-in
            user, a database session, and so on).
        response: The response head the render declares.
    """

    url: str = "/"
    request: Any = None
    locals: dict[str, Any] = field(default_factory=dict)
    response: ResponseHead = field(default_factory=ResponseHead)


def get_request_event() -> RequestEvent | None:
    """Return the request being server-rendered, or `None` in the browser."""
    session = _core._session
    if session is None or session.mode != "server":
        return None
    event = session.event
    return event if isinstance(event, RequestEvent) else None


def _retract(event: RequestEvent, entries: list[Any], entry: Any) -> None:
    owner = _core._current_owner
    if owner is None:
        return
    head = event.response

    def undo() -> None:
        if not head.committed and entry in entries:
            entries.remove(entry)
            head._recompute()

    owner._add_cleanup(undo)


def http_status(code: int, text: str | None = None) -> None:
    """Declare the response status while the calling scope is alive (server only).

    The most recent live declaration wins. When the declaring scope is
    disposed before the head is committed, its declaration is removed
    and the status falls back to the latest one still alive.

    Args:
        code: The HTTP status code.
        text: An optional reason phrase.
    """
    event = get_request_event()
    if event is None or event.response.committed:
        return
    head = event.response
    head._declare()
    entry = (object(), code, text)
    head._statuses.append(entry)
    head._recompute()
    _retract(event, head._statuses, entry)


def http_header(name: str, value: str, *, append: bool = False) -> None:
    """Declare a response header while the calling scope is alive (server only).

    Args:
        name: The header name (case-insensitive).
        value: The header value.
        append: Add another value instead of replacing existing ones
            (for `set-cookie`, say).
    """
    event = get_request_event()
    if event is None or event.response.committed:
        return
    head = event.response
    head._declare()
    entry = (object(), name.lower(), value, append)
    head._headers.append(entry)
    head._recompute()
    _retract(event, head._headers, entry)
