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
from wybthon import Route, Router, component, p

@component
def Home():
    return p("Welcome")

def app():
    return Router([Route("/", Home)])
```

`index.html` marks the region the rendered markup replaces:

```html
<div id="app"><!-- wyb:app --><p id="wyb-loading">Loading...</p><!-- /wyb:app --></div>
```

Prerendering imports your application in a fresh CPython process, so module-level code must run outside the browser. Import `js` and `pyodide` inside the functions that need them, and use [`is_server`][wybthon.is_server] to choose server-safe behavior.

## Rendering on request

Render per request from any Python web framework with [`wybthon.server`](../api/server.md):

```python
from wybthon.server import render_to_string_async

async def page(request):
    body = await render_to_string_async(App(), url=request.url.path)
    return HTMLResponse(TEMPLATE.replace("<!-- app -->", body))
```

| Function | Async data | Use it when |
| --- | --- | --- |
| `render_to_string(view, url=...)` | Not loaded; `Loading` fallbacks render and the browser loads the data | The page has no async data, or it's cheaper to load in the browser |
| `await render_to_string_async(view, url=...)` | Resolved and embedded | You want complete HTML in one response |
| `render_to_stream(view, url=...)` | Streamed per boundary | You want the page to appear before slow data arrives |

The functions return the *contents* of the mount container. They always end with a `<script type="application/json" data-wyb-state>` element that carries the resolved data to the browser; `hydrate` reads it and removes it.

`view` can be a VNode such as `App()` or a zero-argument function that returns one. Renders can run concurrently on one event loop. Don't render from several threads at once.

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

## Async data

`render_to_string_async` and `render_to_stream` run the tree in passes. Each pass renders with the data resolved so far and waits for the async memos it started. A pass can start memos that only render once earlier data has arrived, so a chain of dependent requests resolves in as many passes as it has levels. The final pass renders with everything available, exactly as the browser will while hydrating.

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

`timeout` (30 seconds by default) bounds the total wait. Whatever hasn't resolved by then renders its fallback and loads in the browser.

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

Hydration never breaks the page. When a node doesn't match, the kernel creates the expected node in place, removes server nodes nobody claimed, and logs a warning in dev mode. `kernel.stats()["hydration_mismatches"]` counts them. A mismatch inside a `Loading` boundary stops at the boundary's end.

Mismatches cost extra DOM work, so avoid them. Hydration assumes the browser's first render matches the server's:

- Don't read the clock, random numbers, or browser-only state during render. Read them in an effect, or wrap the UI in [`client_only`][wybthon.client_only].
- Use [`create_unique_id`][wybthon.create_unique_id] for `id` and `for` pairs. Ids created while rendering come from the component's position in the tree, so the server and browser agree.
- Pass the same view, and for request-time rendering, the same URL the browser will show.

```python
from wybthon import client_only

client_only(lambda: MapWidget(lat=lat, lng=lng), fallback=p("Loading map..."))
```

`client_only` renders its fallback on the server and while hydrating, then swaps in its children once hydration has committed.

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
