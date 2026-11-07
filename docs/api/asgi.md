### wybthon.asgi

::: wybthon.asgi

#### What's in this module

| Name | Description |
| --- | --- |
| [`create_app`][wybthon.asgi.create_app] | `create_app(project=None, *, dist=None, dev=False)`: the ASGI app for a `server = true` build. |
| [`App`][wybthon.asgi.App] | The application: pages, server functions, form posts, HTTP handlers, and assets. |
| [`Request`][wybthon.asgi.Request] | `event.request` on the server: `method`, `path`, `query`, `headers`, `body`, `json()`, `form()`. |
| [`Response`][wybthon.asgi.Response] | What middleware and HTTP handlers return: `body`, `status`, `headers`, `cookies`. |

```bash
wyb serve --build
WYBTHON_PROJECT=. uvicorn --factory wybthon.asgi:create_app
```

#### See also

- [Concepts: Full-stack apps](../concepts/full-stack.md)
- [Guides: Deployment](../guides/deployment.md)
- [Testing](testing.md): `Client` sends requests to an app in-process
