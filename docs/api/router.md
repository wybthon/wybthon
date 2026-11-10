### wybthon.router

::: wybthon.router

#### What's in this module

Routing and the data layer, as in Solid Router 2.0. Import it from `wybthon.router`; these names aren't re-exported from `wybthon`. A route's component declares the route props it needs (`params`, `search`, `data`, and `children`) as parameters, and the router passes only those. Only a change in *which* route matches remounts a route; param and search changes flow into the mounted component as prop updates.

| Name | Description |
| --- | --- |
| [`create_router`][wybthon.router.create_router] | `create_router(routes, *, base="", preload_links=True)`: the app's [`Router`][wybthon.router.Router]. Call it to render: `router()`, or `router(root=Shell)` with a root layout. |
| [`Route`][wybthon.router.Route] | `Route(path, component=None, children=[], preload=None)`. Patterns: `:id`, `:id?`, and a final `*name` catch-all. |
| [`PreloadArgs`][wybthon.router.PreloadArgs] | What a route's `preload` receives: `params`, `location`, and `intent`. |
| [`Outlet`][wybthon.router.Outlet] | The matched child route, inside a layout. |
| [`file_routes`][wybthon.router.file_routes] | `file_routes("app.routes")`: a route tree from a package of route modules. |
| [`navigate`][wybthon.router.navigate] | `navigate(path, *, replace=False, scroll=True)`. |
| [`use_params`][wybthon.router.use_params] | Tracked accessor for the path parameters. |
| [`use_search_params`][wybthon.router.use_search_params] | `(search, set_search)`: the [`SearchParams`][wybthon.router.SearchParams] and a merging setter. |
| [`use_location`][wybthon.router.use_location] | The URL: `.path`, `.search`, `.hash`, `.query`, `.href`, each a tracked read. [`url`][wybthon.router.url] is the raw accessor. |
| [`use_route_matches`][wybthon.router.use_route_matches] | Tracked accessor for the matched routes, root to leaf. |
| [`use_link_state`][wybthon.router.use_link_state] | `use_link_state(href, *, end=False)`: `.active()` and `.current()` accessors for styling links. |
| [`preload_route`][wybthon.router.preload_route] | Preload a route's code and data from code. |
| [`query`][wybthon.router.query], [`revalidate`][wybthon.router.revalidate] | Deduplicated, revalidating reads. |
| [`form_action`][wybthon.router.form_action], [`use_submissions`][wybthon.router.use_submissions] | Actions a form posts to, and their settled submissions. |
| [`match_route`][wybthon.router.match_route], [`RouteSpec`][wybthon.router.RouteSpec] | Matching without a browser. |

Links are plain `<a href>` elements: the router follows same-origin clicks under its base path and leaves modifier-key clicks, `target`, `download`, `rel="external"`, and other origins to the browser.

```python
from wybthon import Children, component, html
from wybthon.router import Route, SearchParams, create_router, use_link_state


@component
def Home():
    return html(t"<h1>Home</h1>")


@component
def User(params: dict[str, str], search: SearchParams):
    return html(t"<h1>User {params['id']} (tab={search.get('tab', 'info')})</h1>")


@component
def NotFound():
    return html(t"<h1>Not found</h1>")


@component
def Shell(children: Children = None):
    users = use_link_state("/users")
    return html(t"""
      <nav><a href="/">Home</a> <a href="/users/1?tab=posts" class={"active" if users.active() else ""}>Ada</a></nav>
      {children}
    """)


router = create_router([Route("/", Home), Route("/users/:id", User), Route("*404", NotFound)])


def app():
    return router(root=Shell)
```

#### See also

- [Concepts: Router](../concepts/router.md)
- [Concepts: Full-stack apps](../concepts/full-stack.md): queries, form actions, and file routes
- [Examples: Router](../examples/router.md)
