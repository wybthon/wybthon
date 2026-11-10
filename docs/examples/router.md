# Router

Routing with [`create_router`][wybthon.router.create_router] and [`Route`][wybthon.router.Route] from `wybthon.router`, including path parameters, search params, a nested layout, a root layout, link styling, and a lazily loaded page.

```python
from wybthon import Children, Errored, Loading, component, html, lazy
from wybthon.router import Route, SearchParams, create_router, use_link_state, use_location


@component
def Home():
    return html(t"<div><h1>Home</h1><p>Welcome.</p></div>")


@component
def About(children: Children):
    # Child routes (here, /about/team) render as the layout's children.
    return html(t"<div><h1>About</h1><p>A small routed app.</p>{children}</div>")


@component
def User(params: dict[str, str], search: SearchParams):
    # Navigating from /users/1 to /users/2 updates `params` in place;
    # the component isn't remounted, and only these two text nodes change.
    return html(t"""
      <div>
        <h1>User {params["user_id"]}</h1>
        <p>Tab: {search.get("tab", "info")}</p>
      </div>
    """)


@component
def NotFound():
    location = use_location()
    return html(t"<div><h1>Not found</h1><p>No page at {location.path}</p></div>")


# Loaded on first visit, or as soon as the pointer rests on a link to it.
Team = lazy(lambda: ("app.about.team", "Page"))


@component
def NavLink(href: str, end: bool = False, children: Children = None):
    state = use_link_state(lambda: href, end=end)
    return html(t"<a href={href} class={'active' if state.active() else ''}>{children}</a>")


def page_failed(err, reset):
    return html(t"<p>Page failed to load: {err()}</p>")


@component
def Shell(children: Children = None):
    return html(t"""
      <div>
        <nav>
          <{NavLink} href="/" end={True}>Home</{NavLink}>
          <{NavLink} href="/about">About</{NavLink}>
          <{NavLink} href="/about/team">Team</{NavLink}>
          <{NavLink} href="/users/1?tab=posts">Ada</{NavLink}>
        </nav>
        {Errored(Loading(children, fallback=html(t"<p>Loading...</p>")), fallback=page_failed)}
      </div>
    """)


router = create_router(
    [
        Route("/", Home),
        Route("/about", About, children=[Route("/"), Route("/team", Team)]),
        Route("/users/:user_id", User),
        Route("*404", NotFound),
    ]
)


def app():
    return router(root=Shell)
```

- Each route's component declares the route props it uses as parameters: `User` takes `params` and `search`, the `About` layout takes `children`, and `Home` takes none. The router passes only what a component declares.
- The links are plain anchors: the router navigates without reloading the page, and leaves modifier-key clicks and links with a `target` to the browser.
- `Route("/about", About, children=[...])` is a layout: `/about` matches through the empty `Route("/")` child, and `/about/team` through the `Team` child. Child paths continue the parent's.
- `router(root=Shell)` keeps `Shell` mounted on every page. The `Loading` boundary covers the lazy page's first load; later navigations are transitions that keep the old page on screen until the new one is ready.
- `*404` matches anything no other route does.

To render this on the server and add data, see [Full-stack apps](../concepts/full-stack.md).
