# Server rendering

A Wybthon page can't do anything until Pyodide has downloaded and started, which takes a second or more even with a warm cache. Server rendering removes that wait from what users see. The same components render to HTML in CPython, the HTML ships with the page, and the browser shows it immediately. When Python is ready, [`hydrate`][wybthon.hydrate] adopts the existing DOM and makes it interactive instead of building it again.

Server rendering also makes pages indexable by search engines and usable before Python loads: links work, and input made before hydration is replayed afterward.

## Prerendering at build time

The quickest way to use it is to prerender routes when you build. List them in `wybthon.toml`:

```toml
entry = "app.main:app"
mount = "#app"
prerender = ["/", "/pricing"]
crawl = true
```

`entry` names a function that returns the root view; the bootstrap renders it into `mount`, or hydrates it when the page was prerendered. With `crawl = true`, the build also renders every in-app link it finds in the rendered pages. Each route is written to `<route>/index.html`, and the client-only shell is written to `200.html` for routes that weren't prerendered. Point your static host's fallback at `200.html`.

```python
from wybthon import component, html
from wybthon.router import Route, Router


@component
def Home():
    return html(t"<p>Welcome</p>")


def app():
    return Router([Route("/", Home)])
```

`index.html` marks the region the rendered markup replaces, and where
the build inserts the tags that start the app:

```html
<div id="app"><!-- wyb:app --><p id="wyb-loading" role="status">Loading...</p><!-- /wyb:app --></div>
<!-- wyb:bootstrap -->
```

At the bootstrap marker, the build inlines the manifest as
`<script type="application/json" id="wyb-manifest">`, so the bootstrap
doesn't fetch it, and adds preload hints: `<link rel="modulepreload">`
for Pyodide's `pyodide.mjs`, and `<link rel="preload" as="fetch"
crossorigin>` for the runtime and application archives. The downloads
start while the browser parses the page, instead of after the
bootstrap runs.

Prerendering imports your application in a fresh CPython 3.14 process, so module-level code must run outside the browser. Import `js` and `pyodide` inside the functions that need them, and use [`is_server`][wybthon.is_server] to choose server-safe behavior.

## Rendering on request

Render per request from any Python web framework with [`wybthon.server`](../api/server.md):

```python
from wybthon.server import render_to_stream


async def page(request):
    body = await render_to_stream(App(), url=request.url.path)
    return HTMLResponse(TEMPLATE.replace("<!-- app -->", body))
```

| Call | Async data | Use it when |
| --- | --- | --- |
| `render_to_string(view, url=...)` | Not loaded; `Loading` fallbacks render and the browser loads the data | The page has no async data, or it's cheaper to load in the browser |
| `await render_to_stream(view, url=...)` | Resolved and embedded | You want complete HTML in one response |
| `async for chunk in render_to_stream(view, url=...)` | Streamed per boundary | You want the page to appear before slow data arrives |

[`render_to_string`][wybthon.server.render_to_string] returns a string. [`render_to_stream`][wybthon.server.render_to_stream] returns a [`RenderStream`][wybthon.server.RenderStream]: await it for the complete HTML, or iterate it for chunks. A stream can be consumed only once, so use one or the other. Both functions also accept `event=`, a [`RequestEvent`][wybthon.RequestEvent] describing the request (see [Status codes and headers](#status-codes-and-headers)).

The output is the *contents* of the mount container. It always ends with a `<script type="application/json" data-wyb-state>` element that carries the resolved data to the browser; `hydrate` reads it and removes it.

`view` can be a VNode such as `App()` or a zero-argument function that returns one. Renders can run concurrently on one event loop. Don't render from several threads at once.

Production builds (`wyb build`) turn dev mode off in the browser before your application imports. A server you run yourself stays in dev mode until you turn it off: call [`set_dev_mode(False)`][wybthon.set_dev_mode] at startup in production to skip dev-only checks and warnings, and read the flag with [`is_dev_mode()`][wybthon.is_dev_mode].

## Streaming

`render_to_stream` yields the page immediately, with a fallback in every [`Loading`](async-loading.md) boundary whose data isn't ready. As each boundary's data arrives, it yields that boundary's content in a `<template>` along with a small inline script that swaps it into place. The last chunk is the state script. Write every chunk inside the mount container, in order:

```python
async def stream(request):
    async def body():
        yield HEAD + '<div id="app">'
        async for chunk in render_to_stream(App(), url=request.url.path):
            yield chunk
        yield "</div>" + TAIL

    return StreamingResponse(body(), media_type="text/html")
```

Boundaries stream independently, and a nested boundary arrives after its parent. [`Reveal`](async-loading.md) ordering is respected: a boundary is sent once it would show its content in the browser.

## Status codes and headers

Components shape the HTTP response while they render. Pass a [`RequestEvent`][wybthon.RequestEvent] to the render function, then read the [`ResponseHead`][wybthon.ResponseHead] on its `response`:

```python
from wybthon import RequestEvent
from wybthon.server import render_to_stream


async def page(request):
    event = RequestEvent(url=request.url.path, request=request, locals={"user": request.user})
    body = await render_to_stream(App(), event=event)
    return HTMLResponse(
        TEMPLATE.replace("<!-- app -->", body),
        status_code=event.response.status,
        headers=dict(event.response.header_items()),
    )
```

`RequestEvent(url, request, locals, response)` carries the URL the router reads, your framework's request object (passed through as is), a `locals` dictionary for per-request values such as the signed-in user, and the response head. `ResponseHead(status, status_text, headers, committed)` starts at status 200 with no headers. Its `headers` map lowercase names to lists of values, and `header_items()` flattens them into `(name, value)` pairs, one per value. When you pass both `url=` and `event=`, `url` wins.

Inside components, three functions work with the request:

- [`get_request_event()`][wybthon.get_request_event] returns the `RequestEvent` being rendered, or `None` in the browser.
- [`http_status(code, text=None)`][wybthon.http_status] sets the status and an optional reason phrase.
- [`http_header(name, value, *, append=False)`][wybthon.http_header] sets a header, replacing earlier values; pass `append=True` to add another value instead (for `set-cookie`, say).

```python
from wybthon import component, get_request_event, html, http_header, http_status


@component
def NotFound():
    http_status(404)
    return html(t"<h1>Not found</h1>")


@component
def Account():
    event = get_request_event()
    user = event.locals.get("user") if event is not None else None
    if user is None:
        http_status(302)
        http_header("location", "/login")
        return html(t"<p>Redirecting...</p>")
    http_header("cache-control", "private, no-store")
    return html(t"<h1>Welcome back, {user}</h1>")
```

`http_status` and `http_header` only act on the server; in the browser they do nothing, so the same component works on both sides. Declarations belong to the reactive scope that made them, as in Solid 2.0. When that scope is disposed before the response is committed (an [`Errored`](error-boundaries.md) boundary showing its fallback, a [`Show`][wybthon.Show] branch switching), the previous status or header is restored. If a component declares a cache header and then raises, the boundary's fallback replaces it and the header is withdrawn; the fallback can declare its own, such as `http_status(500)`.

The head is committed when `render_to_string` returns, when an awaited `render_to_stream` finishes, or when a stream yields its first chunk. `event.response.committed` is then `True`, and later declarations are ignored. A streamed response's status and headers must therefore be declared by the shell, outside any `Loading` boundary that's still pending when the first chunk is ready. When streaming, take the first chunk from the stream, then read `event.response` to send the status line and headers before writing the chunk.

See the [`request`](../api/request.md) API reference.

## Async data

`render_to_stream` runs the tree in passes, whether you await it or iterate it. Each pass renders with the data resolved so far and waits for the async memos it started. A pass can start memos that only render once earlier data has arrived, so a chain of dependent requests resolves in as many passes as it has levels. The final pass renders with everything available, exactly as the browser will while hydrating.

The browser starts each memo with the server's value instead of raising `NotReadyError`, so it neither shows a fallback nor fetches the data again. How a memo gets there depends on its shape:

```python
# Preferred: the memo returns a coroutine. While hydrating, Wybthon runs the
# function to track user_id(), then discards the coroutine without running it.
user = create_memo(lambda: fetch_user(user_id()))


# An async def body's reads are only discoverable by running it, so it re-runs
# quietly in the background after hydration, keeping the server value on screen.
async def load_user():
    return await fetch_user(user_id())


user = create_memo(load_user)
```

Choose per memo where the data resolves with `ssr_source`:

| `ssr_source` | On the server | While hydrating |
| --- | --- | --- |
| `"server"` (default) | Resolved and serialized | Uses the serialized value |
| `"hybrid"` | Resolved and serialized | Uses the serialized value, then re-runs quietly |
| `"client"` | Never runs; its boundary renders a fallback | Runs normally |

```python
recommendations = create_memo(lambda: fetch_recommendations(), ssr_source="client")
```

Serialized values must be JSON-compatible: dictionaries, lists, strings, numbers, booleans, and `None`. Tuples arrive as lists. A value that can't be serialized is skipped with a dev-mode warning, and the browser loads it itself.

When an async memo fails on the server, the failure is serialized too. The browser raises it as a [`ServerError`][wybthon.ServerError] carrying the original type name and message, so an [`Errored`](error-boundaries.md) boundary shows the same fallback on both sides. Resetting the boundary runs the work again in the browser.

`render_to_stream`'s `timeout` (30 seconds by default) bounds the total wait. Whatever hasn't resolved by then renders its fallback and loads in the browser.

A memo that uses browser APIs can't run on the server. Use `ssr_source="client"`, or branch on [`is_server`][wybthon.is_server]:

```python
async def load_user():
    if is_server():
        return await database.users.get(user_id())
    return await fetch_json(f"/api/users/{user_id()}")
```

## Hydration

```python
from wybthon import hydrate

hydrate(App(), "#app")
```

The production bootstrap calls `hydrate` automatically when the page contains server state. `hydrate` mounts the tree exactly as [`render`][wybthon.render] would, except that each node *claims* the node the server already rendered instead of creating one. Event handlers, refs, and reactive bindings attach to the existing nodes, and the whole mount is still a single call into JavaScript.

Templates need nothing special. A server render and a hydrating client
expand each template into the same VNodes the element helpers would
build, so the markup and hydration keys match whichever style a
component uses. Once hydration has committed, browser updates use the
compiled path. See
[Templates](templates.md#server-rendering-hydration-and-svg).

Hydration never breaks the page. When a node doesn't match, the kernel creates the expected node in place, removes server nodes nobody claimed, and logs a console warning for the first few mismatches. `kernel.stats()["hydration_mismatches"]` counts them. A mismatch inside a `Loading` boundary stops at the boundary's end.

Mismatches cost extra DOM work, so avoid them. Hydration assumes the browser's first render matches the server's:

- Don't read the clock, random numbers, or browser-only state during render. Read them in an effect, or wrap the UI in [`client_only`][wybthon.client_only].
- Use [`create_unique_id`][wybthon.create_unique_id] for `id` and `for` pairs. Ids created while rendering come from the component's position in the tree, so the server and browser agree.
- Pass the same view, and for request-time rendering, the same URL the browser will show.

```python
from wybthon import client_only, html

client_only(MapWidget(lat=lat, lng=lng), fallback=html(t"<p>Loading map...</p>"))
```

`client_only` renders its fallback on the server and while hydrating, then swaps in its children once hydration has committed.

[`is_hydrating()`][wybthon.is_hydrating] is `True` only during the synchronous mount that `hydrate` performs. Use it to render what the server rendered, then switch to a browser-only value once the page is live:

```python
from wybthon import component, create_signal, html, is_hydrating, is_server, on_settled


@component
def LocalTime():
    initial = "" if is_server() or is_hydrating() else local_time()
    time, set_time = create_signal(initial)
    on_settled(lambda: set_time(local_time()))
    return html(t"<span>{time}</span>")
```

In a page that wasn't server-rendered, `is_hydrating()` is `False` and the component shows the time on its first render.

### Static regions with `NoHydration`

Some content never changes after the first paint: an article body, a footer, legal text. Wrap it in [`NoHydration`][wybthon.NoHydration] and the browser skips it while hydrating:

```python
from wybthon import NoHydration, component, html


@component
def Post():
    static = html(t"""
      <article><p>A long, static article body...</p></article>
      <footer><p>Copyright 2026</p></footer>
    """)
    return html(t"<div>{LikeButton()}{NoHydration(static)}</div>")
```

On the server, `NoHydration(*children)` renders its children normally, between two marker comments. While hydrating, the kernel claims the whole marked region as is, with one command, and nothing inside it is mounted: no components run, no handlers attach, and it costs no Python work. The region never updates afterward, so don't put reactive content, event handlers, or refs inside it. In a page that wasn't server-rendered, the children render normally.

[`Hydration(*children, id=None)`][wybthon.Hydration] is provided for parity with Solid 2.0, where it re-enables hydration for an island inside `NoHydration`. In Wybthon it renders its children unchanged: a `NoHydration` region stays static as a whole, so put interactive islands beside it rather than inside it.

## What changes on the server

- `create_effect`, `create_tracked_effect`, and `on_settled` don't run. Holes and prop bindings evaluate once as the tree mounts.
- [`Portal`](../api/portal.md) renders nothing. Its children mount in the browser after hydration.
- The router reads the `url` passed to the render function, and `navigate` does nothing.
- `lazy` components import their modules directly; chunks are only fetched in the browser.

## Input before hydration

The production bootstrap records clicks, input, changes, key presses, and form submissions that happen before hydration. It prevents submissions from navigating away, and once the page is hydrated it replays the recorded events through the normal delegated handlers. A value typed into an input before hydration is restored before its events replay.

## Limitations

- Derived and projected stores with async bodies (`create_store(fn)` and `create_projection`) aren't serialized yet; they load in the browser after hydration.
- `lazy` components that load a chunk render their `Loading` fallback while hydrating unless the chunk was preloaded.
- Server rendering runs the ordinary renderer against an in-memory DOM. It's fast enough for prerendering and moderate request rates, but it costs more per request than concatenating strings would.

See [RFC 0001](../rfcs/0001-server-rendering-and-hydration.md) for the design and its tradeoffs.
