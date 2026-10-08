### wybthon.request

::: wybthon.request

#### What's in this module

The request a server render is answering, and the response head it
declares. Components call these helpers while they render on the
server; in the browser they're harmless no-ops. Every name here is also
exported from `wybthon`, matching Solid 2.0's `getRequestEvent`,
`httpStatus`, and `httpHeader`.

| Name | Description |
| --- | --- |
| [`RequestEvent`][wybthon.request.RequestEvent] | `RequestEvent(url="/", request=None, locals={}, response=ResponseHead())`: pass it to a [server render](server.md) and read `response` afterward. |
| [`ResponseHead`][wybthon.request.ResponseHead] | `status`, `status_text`, `headers` (lowercase name to a list of values), `committed`, and `header_items()` for an HTTP response. |
| [`get_request_event`][wybthon.request.get_request_event] | The `RequestEvent` being rendered, or `None` in the browser. |
| [`http_status`][wybthon.request.http_status] | `http_status(code, text=None)`: declare the response status. |
| [`http_header`][wybthon.request.http_header] | `http_header(name, value, *, append=False)`: declare a header; `append=True` adds another value (for `set-cookie`). |

Declarations belong to the reactive scope that made them. When that
scope is disposed before the response is committed (an error boundary
recovering, a `Show` switching branches), the previous status or header
is restored. The head is committed once the render finishes, or when a
stream sends its shell; later declarations are ignored.

```python
from wybthon import RequestEvent, component, get_request_event, h1, http_header, http_status, p
from wybthon.server import render_to_string


@component
def NotFound():
    http_status(404)
    return h1("Not found")


@component
def Greeting():
    event = get_request_event()
    user = event.locals.get("user") if event is not None else None
    http_header("Vary", "Cookie")
    return p("Hello, ", user or "guest")


event = RequestEvent(url="/missing", locals={"user": "Ada"})
body = render_to_string(NotFound(), event=event)
event.response.status  # 404
event.response.header_items()  # [] for NotFound; [("vary", "Cookie")] for Greeting
```

#### See also

- [Server](server.md): `render_to_string` and `render_to_stream`
- [Router](router.md): render `http_status(404)` from a `not_found` component
- [Concepts: Server rendering](../concepts/server-rendering.md)
