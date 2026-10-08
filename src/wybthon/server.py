"""Render components to HTML on the server, for hydration in the browser.

Wybthon components are plain Python, so the same code that runs in the
browser under Pyodide renders to HTML in CPython. Serve that HTML with
the page, and the browser shows content immediately instead of waiting
for Pyodide to boot. Once it has, [`hydrate`][wybthon.hydrate] adopts
the server's DOM and makes it interactive.

Two entry points cover the common deployment shapes, as in Solid 2.0:

- [`render_to_string`][wybthon.server.render_to_string] renders
  synchronously. Async data isn't loaded; its
  [`Loading`][wybthon.Loading] boundaries render their fallbacks and
  the browser loads it after hydration.
- [`render_to_stream`][wybthon.server.render_to_stream] sends the page
  with fallbacks immediately, then streams each boundary's content as
  its data arrives. Awaiting it instead waits for every async memo the
  page reads (including memos that only appear once other data arrives)
  and returns the complete HTML with the results embedded, so the
  browser neither fetches them again nor shows a loading state.

Both return (or yield) the *contents* of the mount container;
the caller writes the surrounding document. Output always ends with a
`<script type="application/json" data-wyb-state>` element, which
`hydrate` reads and removes.

Example:
    With any ASGI framework:

    ```python
    from wybthon import RequestEvent
    from wybthon.server import render_to_stream

    async def page(request):
        event = RequestEvent(url=str(request.url.path), request=request)
        body = await render_to_stream(App(), event=event)
        return HTMLResponse(
            TEMPLATE.replace("<!-- app -->", body),
            status_code=event.response.status,
            headers=dict(event.response.header_items()),
        )
    ```

Components declare the response status and headers with
[`http_status`][wybthon.http_status] and
[`http_header`][wybthon.http_header], and read the request with
[`get_request_event`][wybthon.get_request_event].

Rendering runs the ordinary renderer against an in-memory DOM, so
server output always matches what the browser's hydration expects.
Renders may run concurrently on one event loop; don't render from
several threads at once.

See Also:
    * [Server rendering](https://wybthon.com/concepts/server-rendering/)
"""

from __future__ import annotations

import asyncio
import json
import threading
from collections.abc import AsyncIterator, Generator
from typing import Any

from . import kernel
from ._server_dom import ServerBackend, ServerElement, html_between, inner_html
from ._warnings import warn_once
from .kernel import OP_CREATE_ELEMENT
from .reactivity import _core
from .reactivity._core import Memo, _function_name
from .reactivity._primitives import resolve
from .reactivity._session import ServerError, Session, encode_state
from .reconciler import Root, _server_render
from .request import RequestEvent
from .vnode import VNode, copy_vnode

__all__ = ["render_to_string", "render_to_stream", "RenderStream"]

# Upper bound on render passes for one request (each pass discovers one
# level of data that only renders once earlier data has arrived).
MAX_PASSES = 32

# Defines ``__wybSwap(key)``: moves a streamed boundary's content from its
# <template> into place between the boundary's comment markers.
_SWAP_SCRIPT = (
    "<script>function __wybSwap(k){var d=document,t=d.getElementById('wyb-t'+k),"
    "w=d.createTreeWalker(d,128),s,n;while(n=w.nextNode())if(n.nodeValue==='wyb:b'+k){s=n;break}"
    "if(!s||!t)return;var e=s.nextSibling;while(e&&!(e.nodeType===8&&e.nodeValue==='/wyb:b'+k))"
    "{var x=e.nextSibling;e.remove();e=x}s.parentNode.insertBefore(t.content,e);t.remove()}</script>"
)

_thread_lock = threading.Lock()


def _backend() -> ServerBackend:
    backend = kernel._backend
    if not isinstance(backend, ServerBackend):
        backend = ServerBackend()
        kernel.set_backend(backend)
    return backend


def _fresh(view: Any) -> Any:
    """A mountable copy of `view` for one pass: call a factory, or copy a VNode tree."""
    if callable(view) and not isinstance(view, VNode):
        return view()
    return copy_vnode(view)


class _Pass:
    """One synchronous render of the whole tree with the data resolved so far."""

    __slots__ = ("session", "root", "container")

    def __init__(self, view: Any, event: RequestEvent, data: _Data, *, resolve_async: bool) -> None:
        backend = _backend()
        self.session = Session(
            "server",
            url=event.url,
            resolve_async=resolve_async,
            values=dict(data.values),
            errors=dict(data.errors),
            event=event,
        )
        self.session.inflight = data.inflight
        with _thread_lock:
            container_id = kernel.alloc_id()
            kernel.emit((OP_CREATE_ELEMENT, container_id, "div"))
            self.root: Root | None = _server_render(_fresh(view), container_id, self.session)
            kernel.commit()
        container = backend.get_node(container_id)
        assert isinstance(container, ServerElement)
        self.container = container

    def html(self) -> str:
        return inner_html(self.container)

    def pending(self) -> list[Memo[Any]]:
        """Keyed async memos whose work is still in flight."""
        return [
            memo
            for _key, memo in self.session.memos
            if not memo._disposed and memo._async is not None and memo._async.awaiting
        ]

    def detach(self, memos: list[Memo[Any]]) -> None:
        """Keep `memos` running after the tree is disposed, so it can't re-render meanwhile."""
        for memo in memos:
            parent = memo._parent
            if parent is not None and parent._children is not None:
                parent._children.pop(id(memo), None)
            memo._parent = None
            memo._provisional = None

    def dispose(self) -> None:
        root, self.root = self.root, None
        if root is not None:
            with _thread_lock:
                root.dispose()


class _Data:
    """Async results accumulated across the passes of one render."""

    __slots__ = ("values", "errors", "private", "inflight")

    def __init__(self) -> None:
        self.values: dict[str, tuple[Any, str]] = {}
        self.errors: dict[str, tuple[str, str]] = {}
        # Keys resolved for the server only (a lazy component's module).
        self.private: set[str] = set()
        # Memos whose work is still running, kept alive across passes so a
        # later pass waits for them instead of starting the work again.
        self.inflight: dict[str, Memo[Any]] = {}

    def collect(self, memos: list[tuple[str, Memo[Any]]]) -> bool:
        """Record settled results; returns True when anything new arrived."""
        progressed = False
        for key, memo in memos:
            if key in self.values or key in self.errors:
                continue
            progressed |= self._record(key, memo)
        return progressed

    def _record(self, key: str, memo: Memo[Any]) -> bool:
        a = memo._async
        if a is None or a.awaiting:
            return False
        error = memo._error
        if error is not None and not isinstance(error, _core.NotReadyError):
            self.errors[key] = (type(error).__name__, str(error))
        elif a.has_value:
            self.values[key] = (memo._value, _function_name(memo._fn))
        else:
            return False
        if memo._ssr == "local":
            self.private.add(key)
        return True

    def collect_inflight(self) -> bool:
        """Record and release every in-flight memo that has settled."""
        progressed = False
        for key, memo in list(self.inflight.items()):
            if memo._async is not None and memo._async.awaiting:
                continue
            progressed |= self._record(key, memo)
            memo.dispose()
            del self.inflight[key]
        return progressed

    def release(self) -> None:
        for memo in self.inflight.values():
            memo.dispose()
        self.inflight.clear()

    def state(self, final: _Pass) -> str:
        """The `data-wyb-state` script for the memos the final pass rendered."""
        values: dict[str, tuple[Any, str]] = {}
        errors: dict[str, tuple[str, str]] = {}
        for key, memo in final.session.memos:
            if memo._ssr in ("client", "local") or key in self.private:
                continue
            if key in self.values:
                value, name = self.values[key]
                try:
                    json.dumps(value)
                except TypeError, ValueError:
                    warn_once(
                        "ssr_state",
                        name,
                        f"The server value of {name} isn't JSON-compatible, so it wasn't sent to the browser; "
                        "the browser will load it again after hydration.",
                    )
                    continue
                values[key] = (value, name)
            elif key in self.errors:
                errors[key] = self.errors[key]
        failed = {
            key: (
                type(error._value).__name__ if not isinstance(error._value, ServerError) else error._value.type_name,
                str(error._value),
            )
            for key, error in final.session.error_boundaries
            if error._value is not None
        }
        return f'<script type="application/json" data-wyb-state>{encode_state(values, errors, failed)}</script>'


async def _settle(memos: list[Memo[Any]], timeout: float, *, first: bool) -> bool:
    """Wait for one (`first`) or all of `memos` to settle; False when the timeout expired first."""
    if timeout <= 0:
        return False

    async def watch(memo: Memo[Any]) -> None:
        try:
            await resolve(memo)
        except Exception:
            pass

    watchers = [asyncio.ensure_future(watch(memo)) for memo in memos]
    try:
        done, _ = await asyncio.wait(
            watchers, timeout=timeout, return_when=asyncio.FIRST_COMPLETED if first else asyncio.ALL_COMPLETED
        )
    finally:
        for watcher in watchers:
            watcher.cancel()
    return bool(done)


def _event(url: str | None, event: RequestEvent | None) -> RequestEvent:
    if event is None:
        return RequestEvent(url=url or "/")
    if url is not None:
        event.url = url
    return event


def render_to_string(view: Any, *, url: str | None = None, event: RequestEvent | None = None) -> str:
    """Render `view` to HTML synchronously.

    Async memos don't start: the [`Loading`][wybthon.Loading]
    boundaries that read them render their fallbacks, and the browser
    loads the data after [`hydrate`][wybthon.hydrate]. Await
    [`render_to_stream`][wybthon.server.render_to_stream] to include
    async data.

    Args:
        view: The root view: a VNode (such as `App()`) or a zero-arg
            callable returning one.
        url: The request path and query, read by the router. Defaults
            to the event's URL, or `"/"`.
        event: The [`RequestEvent`][wybthon.RequestEvent] being
            rendered; read its `response` afterward for the status and
            headers the page declared.

    Returns:
        The HTML for the mount container's contents, ending with the
        serialized state script.
    """
    event = _event(url, event)
    _core._server_depth += 1
    try:
        data = _Data()
        final = _Pass(view, event, data, resolve_async=False)
        try:
            data.collect(final.session.memos)
            html = final.html() + data.state(final)
            event.response.committed = True
            return html
        finally:
            final.dispose()
    finally:
        _core._server_depth -= 1


async def _render_complete(view: Any, event: RequestEvent, timeout: float) -> str:
    """Render once every async memo the page reads has resolved (the awaited stream)."""
    _core._server_depth += 1
    try:
        final, data = await _resolve(view, event, timeout)
        try:
            html = final.html() + data.state(final)
            event.response.committed = True
            return html
        finally:
            final.dispose()
    finally:
        _core._server_depth -= 1


async def _resolve(
    view: Any, event: RequestEvent, timeout: float, on_pass: Any = None, *, stream: bool = False
) -> tuple[_Pass, _Data]:
    """Render passes until no async work is pending; returns the final pass.

    A stream starts the next pass as soon as any work settles, so fast
    boundaries don't wait for slow ones; otherwise each pass waits for
    all of its work. Work still running carries over to the next pass.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    data = _Data()
    try:
        for _ in range(MAX_PASSES):
            current = _Pass(view, event, data, resolve_async=True)
            if on_pass is not None:
                on_pass(current)
            data.collect(current.session.memos)
            launched = current.pending()
            if not launched and not data.inflight:
                return current, data
            current.detach(launched)
            for memo in launched:
                data.inflight[memo._hk or str(id(memo))] = memo
            current.dispose()
            settled = await _settle(list(data.inflight.values()), deadline - loop.time(), first=stream)
            progressed = data.collect_inflight()
            if not settled or not progressed:
                break
        data.release()
        final = _Pass(view, event, data, resolve_async=False)
        if on_pass is not None:
            on_pass(final)
        data.collect(final.session.memos)
        return final, data
    finally:
        data.release()


class RenderStream:
    """The result of [`render_to_stream`][wybthon.server.render_to_stream].

    Iterate it (`async for chunk in stream`) to send the page as it
    renders, or await it (`html = await stream`) for the complete HTML
    once every async memo has resolved. Use one or the other, once.
    """

    __slots__ = ("_view", "_event", "_timeout", "_used")

    def __init__(self, view: Any, event: RequestEvent, timeout: float) -> None:
        self._view = view
        self._event = event
        self._timeout = timeout
        self._used = False

    def _claim(self) -> None:
        if self._used:
            raise RuntimeError("A render stream can be consumed only once: iterate it or await it")
        self._used = True

    def __aiter__(self) -> AsyncIterator[str]:
        self._claim()
        return self._chunks()

    def __await__(self) -> Generator[Any, None, str]:
        self._claim()
        return _render_complete(self._view, self._event, self._timeout).__await__()

    async def _chunks(self) -> AsyncIterator[str]:
        event = self._event
        _core._server_depth += 1
        try:
            stream = _Stream()
            queue: asyncio.Queue[str | None] = asyncio.Queue()

            def on_pass(current: _Pass) -> None:
                chunk = stream.advance(current)
                if chunk:
                    # The shell carries the response head with it: commit it
                    # before this pass is disposed, which would retract the
                    # declarations it made.
                    event.response.committed = True
                    queue.put_nowait(chunk)

            task = asyncio.ensure_future(_resolve(self._view, event, self._timeout, on_pass, stream=True))
            task.add_done_callback(lambda _task: queue.put_nowait(None))
            try:
                while (chunk := await queue.get()) is not None:
                    yield chunk
                final, data = task.result()
                try:
                    yield data.state(final)
                finally:
                    final.dispose()
            finally:
                if not task.done():
                    task.cancel()
        finally:
            _core._server_depth -= 1


def render_to_stream(
    view: Any, *, url: str | None = None, event: RequestEvent | None = None, timeout: float = 30.0
) -> RenderStream:
    """Render `view` as a stream of HTML, or await it for the complete page.

    Iterating the result yields the page first, with a fallback in every
    boundary whose data isn't ready. Each later chunk carries the content
    of the boundaries that became ready, as `<template>` elements plus a
    small inline script that swaps them into place (out-of-order
    streaming). The last chunk is the serialized state for
    [`hydrate`][wybthon.hydrate]. Write every chunk inside the mount
    container, in order. [`Reveal`][wybthon.Reveal] ordering is
    respected: a boundary is sent once it would show its content in the
    browser. The response head is committed with the first chunk.

    Awaiting the result renders in passes instead: each pass renders with
    the values resolved so far, then waits for the async memos it
    started, and a later pass can start memos that only render once
    earlier data has arrived. The final pass renders synchronously, as
    the browser will while hydrating, and returns the complete HTML with
    its values serialized.

    Args:
        view: The root view: a VNode (such as `App()`) or a zero-arg
            callable returning one.
        url: The request path and query, read by the router. Defaults
            to the event's URL, or `"/"`.
        event: The [`RequestEvent`][wybthon.RequestEvent] being
            rendered; read its `response` for the declared status and
            headers.
        timeout: Seconds to wait for data in total. Boundaries still
            pending then keep their fallbacks and load in the browser.

    Returns:
        A [`RenderStream`][wybthon.server.RenderStream].
    """
    return RenderStream(view, _event(url, event), timeout)


class _Stream:
    """What the browser has received so far: the shell, then boundary swaps."""

    __slots__ = ("shown", "started", "defined")

    def __init__(self) -> None:
        # Boundary key -> the mode the streamed document shows for it.
        self.shown: dict[str, str] = {}
        self.started = False
        self.defined = False

    def advance(self, current: _Pass) -> str:
        backend = _backend()
        boundaries = []
        for key, fragment, mode in current.session.boundaries:
            start = backend.get_node(fragment.el) if fragment.el is not None else None
            end = backend.get_node(fragment._frag_end) if fragment._frag_end is not None else None
            if start is not None and end is not None and _inside(start, current.container):
                boundaries.append((key, start, end, mode._value))
        if not self.started:
            self.started = True
            for key, _start, _end, value in boundaries:
                self.shown[key] = value
            return current.html()
        parts: list[str] = []
        for key, start, end, value in boundaries:
            if self.shown.get(key, "content") == "content" or value != "content":
                continue
            parts.append(f'<template id="wyb-t{key}">{html_between(start, end)}</template>')
            parts.append(f'<script>__wybSwap("{key}")</script>')
            self.shown[key] = "content"
            for nested_key, nested_start, _nested_end, nested_value in boundaries:
                if nested_key not in self.shown and _between(nested_start, start, end):
                    self.shown[nested_key] = nested_value
        if not parts:
            return ""
        if not self.defined:
            self.defined = True
            parts.insert(0, _SWAP_SCRIPT)
        return "".join(parts)


def _inside(node: Any, container: Any) -> bool:
    while node is not None:
        if node is container:
            return True
        node = node.parentNode
    return False


def _between(node: Any, start: Any, end: Any) -> bool:
    """Whether `node` lies strictly between two sibling markers (at any depth)."""
    parent = start.parentNode
    while node is not None and node.parentNode is not parent:
        node = node.parentNode
    if node is None:
        return False
    sibling = start.nextSibling
    while sibling is not None and sibling is not end:
        if sibling is node:
            return True
        sibling = sibling.nextSibling
    return False
