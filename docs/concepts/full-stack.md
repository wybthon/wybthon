# Full-stack apps

A Wybthon app can be one Python codebase for the browser and the server. The server renders every page per request, so it shows before Pyodide boots, and runs the app's [server functions](#server-functions): `async def`s that the browser calls as if they were local. The router's [queries](#queries) read data through them, and its [form actions](#form-actions) change it, with forms that work before Python has started in the browser. This is Solid 2.0's model: `"use server"`, `query`, and `formAction`, with Python on both ends.

## A project

```bash
wyb init my-app --server
cd my-app
wyb dev --open
```

The starter has file routes, a query, and a form action. Its `wybthon.toml` turns the server on:

```toml
entry = "app.main:app"
server = true
server-only = ["app/server/**"]
```

| Setting | Meaning |
| --- | --- |
| `server` | Render pages per request and serve server functions. `wyb dev` and `wyb serve` need it to do either, and a build that finds server functions without it fails. |
| `server-only` | Glob patterns of modules that never reach the browser, such as database code. |
| `middleware` | `module:function` names run around every request (see [Middleware](#middleware)). |
| `routes` | The file routes directory, when it isn't `<app-dir>/routes`. |

`wyb dev` serves the app with pages rendered per request, rebuilds when a file changes, re-imports the server's modules, and updates the open page in place. `wyb build` writes the production build, and `wyb serve` serves it (see [Serving](#serving)).

## Server functions

[`server_function`][wybthon.server_function] makes an `async def` run on the server wherever it's called from:

```python
from dataclasses import dataclass

from wybthon import server_function


@dataclass
class Todo:
    id: int
    title: str
    done: bool = False


@server_function
async def complete(todo_id: int) -> Todo:
    from app.server.db import todos  # never imported in the browser

    return await todos.complete(todo_id)
```

Call it like any coroutine: `todo = await complete(3)`. On the server (while a page renders, or inside another server function), the call runs the function directly. In the browser, it posts the arguments to `{base}_wyb/fn/app.todos:complete` and returns the answer.

- **What reaches the browser.** The build replaces the body of every server function with `...` in the browser's copy of the module, and removes each import only those bodies used, so `app.server.db` isn't imported (or shipped, being `server-only`) in the browser. Line numbers don't change, so tracebacks still point at the right lines.
- **Arguments and results** cross in Wybthon's wire format: JSON, plus dataclasses, enums, tuples, sets, `datetime`, `date`, `time`, `timedelta`, `Decimal`, `UUID`, and `bytes`. On the server, every argument is rebuilt and checked against the function's own annotations, so `complete("3")` is a 400, not a string where an `int` should be, and a client can't make the server build anything the function didn't declare. Annotate every parameter.
- **Errors.** An exception the function raises arrives in the browser as [`ServerError`][wybthon.ServerError], with the exception's type name in `type_name`. In development its message comes along; in production only a `ServerError` the function raised itself carries its message, so internal details don't leak. Raise `ServerError("Message for the user", "PermissionError")` for errors meant for the page.
- **Where it's defined.** A server function must be a module-level `async def`, so the browser and the server name it the same way: `module:qualname`.
- **The request.** [`get_request_event()`][wybthon.get_request_event] returns the request the call came in with. Read `event.headers` and `event.cookies`, use `event.locals` for what middleware set, and call [`set_cookie`][wybthon.set_cookie] or [`http_header`][wybthon.http_header] to shape the response.
- **Security.** A call from a script carries an `x-wyb-fn` header, which a page on another origin can't add without the server's permission. A form post, which can't carry a header, must come from the same origin (by `Sec-Fetch-Site` or `Origin`). Authorization is still yours: check the user in every server function that needs it.

### Mutations and reads

A server function is called with POST by default, and a POST is a mutation: when it completes, the browser revalidates every [query](#queries) on the page, so what's shown reflects the change. Declare a read with `@server_function(method="GET")`; a server function wrapped in `query` is a GET automatically.

### Responses

Raise or return one of these to do more than return a value:

| Helper | Effect |
| --- | --- |
| [`redirect(url, status=302, *, revalidate=None)`][wybthon.redirect] | The browser navigates to `url`. While a page renders on the server, it's the page's HTTP redirect. A JavaScript-free form post gets a `303` to it. |
| [`reload(*, revalidate=None)`][wybthon.reload] | Revalidate queries without navigating. |
| [`respond(value, *, status=200, headers=None, revalidate=None)`][wybthon.respond] | Return `value` with a status and headers. |

`revalidate` names the query keys (or key prefixes) a call changed; omit it to revalidate everything on the page, and pass `""` to revalidate nothing:

```python
@server_function
async def log_search(term: str) -> None:
    await analytics.record(term)
    return respond(revalidate="")
```

## Queries

[`query`][wybthon.router.query] wraps an async read so its calls are deduplicated and refetch when they're revalidated. Read one in an async memo, under a [`Loading`][wybthon.Loading] boundary:

```python
from wybthon import For, Loading, component, create_memo, html, server_function
from wybthon.router import query


@query
@server_function
async def list_todos() -> list[Todo]:
    from app.server.db import todos

    return await todos.all()


@component
def Todos():
    todos = create_memo(lambda: list_todos())

    def row(todo, _index):
        return html(t"<li>{todo.title}</li>")

    return Loading(html(t"<ul>{For(todos(), row)}</ul>"), fallback=html(t"<p>Loading...</p>"))
```

A query:

1. dedupes calls on the server for the lifetime of a request, so components that read the same data don't fetch it twice;
2. reuses a result in the browser for five seconds after it arrives, so a link's [preload](router.md#preloading) and the page it opens share one fetch;
3. refetches, in every memo that read it, when [`revalidate`][wybthon.router.revalidate] names its key, or when a mutation completes. A memo that already shows data keeps showing it until the new data arrives.

A query's key defaults to its server function's id, or the function's module and name; pass one explicitly with `@query("todos")` or `query(fn, "todos")`. A call's full key is the query's key followed by its arguments, and `revalidate` matches by prefix: `revalidate(get_user)` (or `revalidate(get_user.key)`) refetches every user, and `revalidate()` refetches every query.

When the server renders a page, the values its queries resolved are sent with the page, so the browser hydrates with them instead of fetching again.

A query doesn't have to wrap a server function: wrap any async read, such as a call to an external API, to get the same deduplication and revalidation.

## Form actions

[`form_action`][wybthon.router.form_action] makes an action that a `<form>` posts to. Put it in the form's `action` attribute:

```python
from wybthon import FormData, server_function
from wybthon.router import form_action


@form_action
@server_function
async def add_todo(form: FormData) -> None:
    from app.server.db import todos

    title = str(form.get("title", "")).strip()
    if not title:
        raise ServerError("A todo needs a title", "ValueError")
    await todos.add(title)


@component
def NewTodo():
    return html(t"""
      <form action={add_todo} method="post">
        <input name="title" required>
        <button disabled={add_todo.pending()}>Add</button>
      </form>
    """)
```

- **With Python running in the browser**, the submit runs the action with the form's [`FormData`][wybthon.FormData] (text fields as `str`, files as [`UploadedFile`][wybthon.UploadedFile]). It's an [action][wybthon.action]: `add_todo.pending()` is true while it runs, [optimistic](async-loading.md) writes made for it revert when it settles, and when it completes, the page's queries revalidate. The form has `aria-busy="true"` meanwhile, for CSS.
- **Before Pyodide has booted**, or without JavaScript, the browser posts the form to the server function's URL. The server runs the action and redirects back to the page (or to where the action redirected), and the submission's result rides along in a short-lived cookie, so [`use_submissions`](#submissions) shows it on the page that loads. A first-time visitor can use the form while Python is still downloading.
- **Bound arguments.** [`action.bind(*args)`][wybthon.router.FormAction.bind] passes arguments ahead of the form data, as Solid's `action.with` does: `<form action={rename.bind(todo.id)} method="post">` calls `rename(todo.id, form)`. They travel in the URL, so they're validated like any other argument.
- **Calling it directly.** A form action is also callable: `await add_todo(form)`.
- **Hooks.** `add_todo.on_submit(fn)` calls `fn(*input)` when a submission starts, inside its transaction (write optimistic state there), and `add_todo.on_settled(fn)` calls `fn(submission)` when one settles. Both belong to the calling owner and go away with it.

A form action that isn't a server function runs in the browser only, so it needs a stable name: `form_action(save_draft, "save-draft")`.

### Submissions

[`use_submissions(action)`][wybthon.router.use_submissions] is a tracked accessor for the action's settled [`Submission`][wybthon.router.Submission]s, oldest first: each has `input` (the arguments, ending with the `FormData`), `result`, `error`, and `url`, and `clear()` and `retry()` methods. It's history, not in-flight state: show in-flight state with `action.pending()` and optimistic primitives.

```python
@component
def Errors():
    submissions = use_submissions(add_todo)

    def message():
        failed = [item for item in submissions() if item.error is not None]
        return str(failed[-1].error) if failed else ""

    return html(t'<p role="alert">{message()}</p>')
```

## File routes

[`file_routes("app.routes")`][wybthon.router.file_routes] turns a package of route modules into a route tree:

```
app/routes/
    _layout.py        the root layout (optional)
    index.py          /
    about.py          /about
    users/
        _layout.py    a layout for everything under /users
        index.py      /users
        [id].py       /users/:id
        [[tab]].py    /users/:tab?    (an optional parameter)
    (marketing)/      a group: organizes files without adding a segment
        pricing.py    /pricing
    [...404].py       anything else
```

A page module defines a `Page` component and may define `preload(args)`. A `_layout.py` defines a `Layout` component, which receives the matched page as `props.children`. Other files starting with `_` are private to the directory, and a module without a `Page` isn't a route. Pages load lazily, so a page's startup imports only what it shows.

```python
from wybthon.router import create_router, file_routes

router = create_router(file_routes("app.routes"))
```

### HTTP handlers

A route module may also define HTTP handlers, for API endpoints: `async def GET(event)`, and likewise `POST`, `PUT`, `PATCH`, and `DELETE`. The ASGI app calls one for a request with that method, except a `GET` from a browser loading a page (one that accepts `text/html`) when the module also has a `Page`. The build removes the handlers from the browser's copy, as it does server functions.

```python
# app/routes/api/todos/[id].py
from wybthon import respond


async def GET(event):
    todo = await db.todos.get(int(event.locals["params"]["id"]))
    return {"id": todo.id, "title": todo.title}


async def DELETE(event):
    await db.todos.delete(int(event.locals["params"]["id"]))
    return respond(status=204)
```

A handler receives the [`RequestEvent`][wybthon.RequestEvent]; `event.request` is the [`Request`][wybthon.asgi.Request] (`method`, `path`, `query`, `headers`, `body`, `json()`, `form()`), and `event.locals["params"]` holds the route's parameters. It returns a dict or list (sent as JSON), a `str`, `bytes`, `None` (204), a [`Response`][wybthon.asgi.Response], or a response helper.

## Serving

| Command | What it serves |
| --- | --- |
| `wyb dev` | The project in development mode, rebuilt and reloaded on change. |
| `wyb serve` | A production build (`wyb serve --build` builds first), with Wybthon's small HTTP server. |
| `WYBTHON_PROJECT=. uvicorn --factory wybthon.asgi:create_app` | The same app under any ASGI server, for production traffic. |

[`create_app(project)`][wybthon.asgi.create_app] returns the ASGI application: it renders pages into the build's page shell, streaming each `Loading` boundary as its data arrives, and serves server functions, HTTP handlers, and the build's assets (content-hashed ones with a year of caching). Routes listed under `prerender` are served from their prerendered HTML.

### Middleware

Middleware runs around every request. List `module:function` names under `middleware` in `wybthon.toml`; each one receives the [`RequestEvent`][wybthon.RequestEvent] and a `call_next` function, and returns a [`Response`][wybthon.asgi.Response]:

```python
from wybthon.asgi import Response


async def authenticate(event, call_next):
    session = event.cookies.get("session")
    event.locals["user"] = await sessions.user_for(session) if session else None
    if event.request.path.startswith("/admin") and event.locals["user"] is None:
        return Response(b"", 303, {"location": "/login"})
    response = await call_next()
    response.headers["x-frame-options"] = "DENY"
    return response
```

Components and server functions read `event.locals` through `get_request_event()`.

## Testing

[`wybthon.testing`][wybthon.testing] covers both sides:

- [`connect_server()`][wybthon.testing.connect_server] makes the components a test renders call their server functions the way the browser does, with arguments encoded, validated, and decoded, in-process.
- [`Client(app)`][wybthon.testing.Client] sends requests to an ASGI app without a network: pages, form posts (`client.post_form(...)`), and HTTP handlers, keeping cookies between requests.

```python
from wybthon.asgi import create_app
from wybthon.testing import Client, connect_server, fire, render, tick


async def test_adding_a_todo():
    with connect_server(), render(TodoPage()) as screen:
        fire.input(screen.get_by_role("textbox"), "Write tests")
        fire.submit(screen.get_by_role("form"))
        await tick(4)
        assert screen.get_by_text("Write tests")


def test_the_form_works_without_javascript():
    client = Client(create_app("."))
    response = client.post_form("/_wyb/fn/app.todos:add_todo", {"title": "Write tests"})
    assert response.status == 303
    assert "Write tests" in client.get("/").text
```

## See also

- [Router](router.md): routes, links, and preloading
- [Server rendering](server-rendering.md): streaming, hydration, and the response head
- [Deployment](../guides/deployment.md)
- [RFC 0008](../rfcs/0008-full-stack.md)
