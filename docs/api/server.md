### wybthon.server

::: wybthon.server

#### What's in this module

Server rendering: the same components that run in the browser render to HTML in CPython. A server render expands each `html` template into the same nodes the element helpers would build, so the output and hydration keys don't depend on which style you used. See [Server rendering](../concepts/server-rendering.md) for the full guide.

| Name | Description |
| --- | --- |
| [`render_to_string`][wybthon.server.render_to_string] | `render_to_string(view, *, url=None, event=None)`: render synchronously. Async data isn't loaded; `Loading` boundaries render their fallbacks. |
| [`render_to_stream`][wybthon.server.render_to_stream] | `render_to_stream(view, *, url=None, event=None, timeout=30)`: returns a `RenderStream`. |
| [`RenderStream`][wybthon.server.RenderStream] | Iterate it (`async for chunk in stream`) for the page with fallbacks, then each `Loading` boundary as its data arrives, then the state. Await it (`html = await stream`) for the complete HTML once every async memo has resolved. Use one or the other, once. |

Awaiting `render_to_stream` replaces the removed `render_to_string_async`.
The browser side, [`hydrate`][wybthon.hydrate], [`is_server`][wybthon.is_server], [`is_hydrating`][wybthon.is_hydrating], [`client_only`][wybthon.client_only], [`NoHydration`][wybthon.NoHydration], and [`ServerError`][wybthon.ServerError], is exported from `wybthon`, as are the [request helpers](request.md) components use to set the status and headers.

```python
import asyncio

from wybthon import RequestEvent, component, html, http_header
from wybthon.server import render_to_stream


@component
def App():
    http_header("Cache-Control", "max-age=60")
    return html(t"<p>Hello from the server</p>")


async def main():
    event = RequestEvent(url="/")
    page = await render_to_stream(App(), event=event)
    print(event.response.status, event.response.headers, page)


asyncio.run(main())
```

#### See also

- [Request](request.md): `RequestEvent`, `http_status`, and `http_header`
- [Concepts: Server rendering](../concepts/server-rendering.md)
- [Guides: Deployment](../guides/deployment.md)
- [RFC 0001](../rfcs/0001-server-rendering-and-hydration.md)
