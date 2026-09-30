### wybthon.server

::: wybthon.server

#### What's in this module

Server rendering: the same components that run in the browser render to HTML in CPython. See [Server rendering](../concepts/server-rendering.md) for the full guide.

| Name | Description |
| --- | --- |
| [`render_to_string`][wybthon.server.render_to_string] | Render synchronously. Async data isn't loaded; `Loading` boundaries render their fallbacks. |
| [`render_to_string_async`][wybthon.server.render_to_string_async] | Resolve every async memo the page reads, then render and embed the results. |
| [`render_to_stream`][wybthon.server.render_to_stream] | Yield the page with fallbacks, then each `Loading` boundary as its data arrives, then the state. |

The browser side, [`hydrate`][wybthon.hydrate], [`is_server`][wybthon.is_server], [`client_only`][wybthon.client_only], and [`ServerError`][wybthon.ServerError], are exported from `wybthon`.

```python
import asyncio
from wybthon import component, p
from wybthon.server import render_to_string_async

@component
def App():
    return p("Hello from the server")

html = asyncio.run(render_to_string_async(App(), url="/"))
```

#### See also

- [Concepts: Server rendering](../concepts/server-rendering.md)
- [Guides: Deployment](../guides/deployment.md)
- [RFC 0001](../rfcs/0001-server-rendering-and-hydration.md)
