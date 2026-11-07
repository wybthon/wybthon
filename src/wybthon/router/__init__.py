"""Routing and the data layer, as in Solid Router 2.0.

Import it from `wybthon.router`:

- **Routes.** [`create_router`][wybthon.router.create_router] takes a
  tree of [`Route`][wybthon.router.Route]s (or
  [`file_routes()`][wybthon.router.file_routes], one module per page) and
  returns the router; call it to render. Plain `<a href>` links navigate
  within the app. [`Outlet`][wybthon.router.Outlet] renders a layout's
  matched child.
- **Reading the URL.** [`use_params`][wybthon.router.use_params],
  [`use_search_params`][wybthon.router.use_search_params],
  [`use_location`][wybthon.router.use_location],
  [`use_route_matches`][wybthon.router.use_route_matches], and
  [`use_link_state`][wybthon.router.use_link_state];
  [`navigate`][wybthon.router.navigate] goes somewhere.
- **Data.** [`query`][wybthon.router.query] wraps an async read so calls
  are deduplicated and refetch on
  [`revalidate`][wybthon.router.revalidate];
  [`form_action`][wybthon.router.form_action] makes an action a form can
  post to, even before Python has booted, and
  [`use_submissions`][wybthon.router.use_submissions] reads its history.

```python
from wybthon import FormData, component, create_memo, html, server_function
from wybthon.router import Route, RouteProps, create_router, form_action, query


@query
@server_function
async def get_user(user_id: int) -> User:
    return await db.users.get(user_id)


@form_action
@server_function
async def rename(user_id: int, form: FormData) -> None:
    await db.users.rename(user_id, form["name"])


@component
def Profile(props: RouteProps):
    user = create_memo(lambda: get_user(int(props.params["id"])))
    return html(t'''
      <h1>{user().name}</h1>
      <form action={rename.bind(user().id)} method="post">
        <input name="name"><button>Rename</button>
      </form>
    ''')


router = create_router([Route("/", Home), Route("/users/:id", Profile), Route("*404", NotFound)])
```

Path matching ([`resolve`][wybthon.router.resolve]) needs no browser, so
it also runs in tests, tools, and on the server.
"""

from ._data import Query, query, revalidate
from ._files import ApiRoute, api_routes, file_routes
from ._forms import FormAction, Submission, form_action, use_submissions
from ._location import Location, SearchParams, navigate, url, use_location
from ._match import RouteSpec, resolve
from ._router import (
    LinkState,
    Outlet,
    PreloadArgs,
    Route,
    RouteProps,
    Router,
    create_router,
    preload_route,
    use_link_state,
    use_params,
    use_route_matches,
    use_search_params,
)

__all__ = [
    "ApiRoute",
    "FormAction",
    "LinkState",
    "Location",
    "Outlet",
    "PreloadArgs",
    "Query",
    "Route",
    "RouteProps",
    "RouteSpec",
    "Router",
    "SearchParams",
    "Submission",
    "api_routes",
    "create_router",
    "file_routes",
    "form_action",
    "navigate",
    "preload_route",
    "query",
    "resolve",
    "revalidate",
    "url",
    "use_link_state",
    "use_location",
    "use_params",
    "use_route_matches",
    "use_search_params",
    "use_submissions",
]
