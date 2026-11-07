### wybthon.server_functions

::: wybthon.server_functions

#### What's in this module

Server functions and the responses they return. Everything here is exported from `wybthon`, as are [`FormData`][wybthon.FormData] and [`UploadedFile`][wybthon.UploadedFile], what a form action receives.

| Name | Description |
| --- | --- |
| [`server_function`][wybthon.server_function] | `@server_function` or `@server_function(method="GET")`: make an `async def` run on the server. |
| [`ServerFunction`][wybthon.ServerFunction] | What the decorator returns; `id` is `module:qualname`, and `url` the URL the browser calls. |
| [`redirect`][wybthon.redirect] | Navigate (or answer a page or a form post with a redirect). |
| [`reload`][wybthon.reload] | Revalidate queries without navigating. |
| [`respond`][wybthon.respond] | Return a value with a status, headers, or the query keys a call changed. |

#### See also

- [Concepts: Full-stack apps](../concepts/full-stack.md)
- [ASGI](asgi.md)
- [Request](request.md): `get_request_event`, `http_header`, and `set_cookie`
