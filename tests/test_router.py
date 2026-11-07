"""The router: routes, plain-anchor navigation, layouts, preloading, and matching."""

import asyncio

import pytest

from wybthon import Loading, component, create_signal, flush, html, http_status, untrack
from wybthon.router import (
    Outlet,
    PreloadArgs,
    Route,
    RouteProps,
    RouteSpec,
    create_router,
    navigate,
    preload_route,
    resolve,
    url,
    use_link_state,
    use_location,
    use_params,
    use_route_matches,
    use_search_params,
)
from wybthon.testing import fire, render


@pytest.fixture(autouse=True)
def reset_location():
    navigate("/")
    flush()
    yield
    navigate("/")
    flush()


@component
def Home():
    return html(t'<div><h1>Home</h1><a href="/users/1">One</a><a href="/about">About</a></div>')


@component
def User(props: RouteProps):
    return html(t"<h1>User {props.params['id']} tab={props.search.get('tab', '-')}</h1>")


@component
def NotFound():
    http_status(404)
    return html(t"<p>nope</p>")


def go(path: str) -> None:
    navigate(path)
    flush()


# ---------------------------------------------------------------------------
# Rendering routes
# ---------------------------------------------------------------------------


def test_router_renders_the_matched_route():
    router = create_router([Route("/", Home), Route("/users/:id", User)])
    with render(router()) as screen:
        assert screen.get_by_role("heading").text_content == "Home"
        go("/users/42?tab=posts")
        assert screen.text() == "User 42 tab=posts"
        go("/")
        assert screen.get_by_role("heading").text_content == "Home"


def test_param_changes_update_props_in_place():
    mounted: list[str] = []

    @component
    def Tracked(props: RouteProps):
        mounted.append(untrack(lambda: props.params["id"]))
        return html(t"<span>{props.params['id']}</span>")

    router = create_router([Route("/users/:id", Tracked)])
    with render(router()) as screen:
        go("/users/1")
        go("/users/2")
        assert screen.text() == "2"
        assert mounted == ["1"]


def test_nothing_matching_renders_nothing_and_a_catch_all_matches():
    router = create_router([Route("/", Home)])
    with render(router()) as screen:
        go("/missing")
        assert screen.text() == ""
    router = create_router([Route("/", Home), Route("*404", NotFound)])
    with render(router()) as screen:
        go("/missing/deeply")
        assert screen.text() == "nope"


def test_a_layout_receives_its_matched_child_as_children_and_outlet():
    mounted: list[str] = []

    @component
    def Layout(props: RouteProps):
        mounted.append("layout")
        return html(t"<section><header>top</header>{props.children}</section>")

    @component
    def OutletLayout():
        return html(t"<div>{Outlet()}</div>")

    @component
    def Overview():
        return html(t"<p>overview</p>")

    @component
    def Settings(props: RouteProps):
        return html(t"<p>settings {props.params['id']}</p>")

    routes = [
        Route("/users/:id", Layout, children=[Route("/", Overview), Route("/settings", Settings)]),
        Route("/o", OutletLayout, children=[Route("/", Overview)]),
    ]
    router = create_router(routes)
    with render(router()) as screen:
        go("/users/3")
        assert screen.text() == "topoverview"
        go("/users/3/settings")
        assert screen.text() == "topsettings 3"
        assert mounted == ["layout"]
        go("/o")
        assert screen.text() == "overview"


def test_a_route_without_a_component_renders_its_children():
    @component
    def Doc(props: RouteProps):
        return html(t"<p>doc {props.params['page']}</p>")

    router = create_router([Route("/docs", children=[Route("/:page", Doc)])])
    with render(router()) as screen:
        go("/docs/intro")
        assert screen.text() == "doc intro"


def test_a_root_layout_stays_mounted_around_every_route():
    mounted: list[int] = []

    @component
    def Shell(props: RouteProps):
        mounted.append(1)
        return html(t"<main><nav>nav</nav>{props.children}</main>")

    router = create_router([Route("/", Home), Route("/users/:id", User)])
    with render(router(root=Shell)) as screen:
        assert "nav" in screen.text()
        go("/users/5")
        assert screen.text() == "navUser 5 tab=-"
        assert mounted == [1]


def test_the_base_path_scopes_matching():
    router = create_router([Route("/", Home), Route("/users/:id", User)], base="/app")
    with render(router()) as screen:
        go("/app/users/9")
        assert screen.text() == "User 9 tab=-"
        go("/elsewhere/users/9")
        assert screen.text() == ""
    assert router.match("/app/users/1")[0].component is User
    assert router.match("/users/1") == []


# ---------------------------------------------------------------------------
# Plain anchors
# ---------------------------------------------------------------------------


def test_a_click_on_a_plain_link_navigates_without_reloading():
    router = create_router([Route("/", Home), Route("/users/:id", User)])
    with render(router()) as screen:
        fire.click(screen.get_by_text("One"))
        assert url.peek() == "/users/1"
        assert screen.text() == "User 1 tab=-"


def test_modifier_clicks_targets_and_downloads_are_left_to_the_browser():
    @component
    def Links():
        return html(t"""<div>
          <a href="/users/1">plain</a>
          <a href="/users/2" target="_blank">blank</a>
          <a href="/users/3" download>file</a>
          <a href="/users/4" rel="external">ext</a>
          <a href="https://example.com/x">other origin</a>
          <a href="#top">hash</a>
        </div>""")

    router = create_router([Route("/", Links), Route("/users/:id", User)])
    with render(router()) as screen:
        fire.click(screen.get_by_text("plain"), meta_key=True)
        fire.click(screen.get_by_text("plain"), button=1)
        for name in ("blank", "file", "ext", "other origin", "hash"):
            fire.click(screen.get_by_text(name))
        assert url.peek() == "/"


def test_a_handler_that_prevents_default_keeps_the_router_out():
    def stay(event):
        event.prevent_default()

    @component
    def Guarded():
        return html(t'<a href="/users/1" onclick={stay}>guarded</a>')

    router = create_router([Route("/", Guarded), Route("/users/:id", User)])
    with render(router()) as screen:
        fire.click(screen.get_by_text("guarded"))
        assert url.peek() == "/"


def test_links_outside_the_base_path_load_normally():
    @component
    def Page():
        return html(t'<div><a href="/app/users/1">inside</a><a href="/docs">outside</a></div>')

    router = create_router([Route("/", Page), Route("/users/:id", User)], base="/app")
    with render(router()) as screen:
        go("/app")
        fire.click(screen.get_by_text("outside"))
        assert url.peek() == "/app"
        fire.click(screen.get_by_text("inside"))
        assert url.peek() == "/app/users/1"


def test_link_state_marks_active_and_current_links():
    @component
    def Nav():
        users = use_link_state("/users")
        exact = use_link_state("/users", end=True)
        home = use_link_state("/")
        query = use_link_state("/users?tab=a")
        label = lambda: f"{users.active()}{exact.active()}{home.active()}{query.current()}"  # noqa: E731
        return html(t"<p>{label()}</p>")

    with render(Nav()) as screen:
        assert screen.text() == "FalseFalseTrueFalse"
        go("/users/3")
        assert screen.text() == "TrueFalseFalseFalse"
        go("/users?tab=a")
        assert screen.text() == "TrueTrueFalseTrue"


# ---------------------------------------------------------------------------
# Reading the URL
# ---------------------------------------------------------------------------


def test_url_hooks_read_params_search_location_and_matches():
    seen: dict[str, object] = {}

    @component
    def Page():
        params = use_params()
        search, set_search = use_search_params()
        location = use_location()
        matches = use_route_matches()
        seen["set"] = set_search
        return html(
            t"<p>{params()['slug']}|{str(search().get_all('t'))}|{location.path}|{location.hash}|{len(matches())}</p>"
        )

    router = create_router([Route("/posts", children=[Route("/:slug", Page)])])
    with render(router()) as screen:
        go("/posts/hello%20world?t=a&t=b#some%20part")
        assert screen.text() == "hello world|['a', 'b']|/posts/hello%20world|some part|2"
        seen["set"](page=2, t=None)
        flush()
        assert url.peek() == "/posts/hello%20world?page=2#some%20part"


def test_url_hooks_outside_a_router():
    seen: dict[str, object] = {}

    @component
    def Lonely():
        seen["params"] = use_params()()
        seen["matches"] = use_route_matches()()
        return html(t"<p>x</p>")

    with render(Lonely()):
        assert seen == {"params": {}, "matches": []}


def test_a_route_table_in_a_template_keeps_route_identity():
    mounted: list[str] = []

    @component
    def Page(props: RouteProps):
        mounted.append(untrack(lambda: props.params["id"]))
        return html(t"<p>page {props.params['id']}</p>")

    router = create_router([Route("/", Home), Route("/p/:id", Page)])
    with render(html(t"<main>{router()}</main>")) as screen:
        go("/p/1")
        go("/p/2")
        assert screen.text() == "page 2"
        assert mounted == ["1"]


# ---------------------------------------------------------------------------
# Preloading
# ---------------------------------------------------------------------------


def test_preload_runs_with_its_intent_and_its_result_is_data():
    calls: list[tuple[dict[str, str], str]] = []

    def preload(args: PreloadArgs) -> str:
        calls.append((args.params, args.intent))
        return f"data for {args.params['id']}"

    @component
    def Page(props: RouteProps):
        return html(t"<p>{props.data}</p>")

    router = create_router([Route("/", Home), Route("/users/:id", Page, preload=preload)])
    with render(router()) as screen:
        go("/users/7")
        assert screen.text() == "data for 7"
        assert calls == [({"id": "7"}, "navigate")]


def test_resting_on_a_link_preloads_its_route():
    calls: list[str] = []

    def preload(args: PreloadArgs) -> None:
        calls.append(args.intent)

    router = create_router([Route("/", Home), Route("/users/:id", User, preload=preload)])
    with render(router()) as screen:
        fire(screen.get_by_text("One"), "pointerover")
        assert calls == ["preload"]
        fire(screen.get_by_text("About"), "pointerover")
        assert calls == ["preload"]

    calls.clear()
    quiet = create_router([Route("/", Home), Route("/users/:id", User, preload=preload)], preload_links=False)
    with render(quiet()) as screen:
        fire(screen.get_by_text("One"), "pointerover")
        assert calls == []


def test_an_async_preload_holds_navigation_and_is_cancelled_with_the_router():
    async def main() -> None:
        gate = asyncio.Event()
        started: list[str] = []
        closed: list[str] = []

        async def preload(args: PreloadArgs) -> None:
            started.append(args.params["id"])
            try:
                await gate.wait()
            finally:
                closed.append(args.params["id"])

        @component
        def Warm():
            def warm() -> None:
                preload_route("/users/1")

            return html(t"<button onclick={warm}>warm</button>")

        router = create_router([Route("/", Warm), Route("/users/:id", User, preload=preload)])
        screen = render(Loading(router(), fallback="wait"))
        fire.click(screen.get_by_text("warm"))
        await asyncio.sleep(0)
        assert started == ["1"]
        go("/users/1")
        await asyncio.sleep(0)
        assert started == ["1"]
        gate.set()
        for _ in range(8):
            await asyncio.sleep(0)
            flush()
        assert screen.text() == "User 1 tab=-"
        gate.clear()
        go("/users/2")
        await asyncio.sleep(0)
        screen.unmount()
        for _ in range(4):
            await asyncio.sleep(0)
        assert closed == ["1", "2"]

    asyncio.run(main())


def test_a_signal_change_still_updates_a_routed_component():
    count, set_count = create_signal(0)

    @component
    def Counter():
        return html(t"<p>{count()}</p>")

    router = create_router([Route("/", Counter)])
    with render(router()) as screen:
        set_count(3)
        flush()
        assert screen.text() == "3"


# ---------------------------------------------------------------------------
# Matching (no browser needed)
# ---------------------------------------------------------------------------


def test_resolve_matches_literals_and_parameters():
    route, info = resolve([RouteSpec("/"), RouteSpec("/about")], "/about")
    assert route.path == "/about" and info["params"] == {}
    route, info = resolve([RouteSpec("/users/:id")], "/users/42/")
    assert info["params"] == {"id": "42"}


def test_resolve_child_paths_continue_their_parent():
    routes = [RouteSpec("/about", children=[RouteSpec("/"), RouteSpec("/team")])]
    route, info = resolve(routes, "/about/team")
    assert route.path == "/team"
    assert [r.path for r in info["matches"]] == ["/about", "/team"]
    route, _ = resolve(routes, "/about")
    assert route.path == "/"
    # A layout matches only through a child.
    assert resolve([RouteSpec("/about", children=[RouteSpec("/team")])], "/about") is None


def test_resolve_catch_alls_and_optional_parameters():
    routes = [RouteSpec("/docs/*rest"), RouteSpec("/u/:id?"), RouteSpec("*")]
    route, info = resolve(routes, "/docs/guide/intro")
    assert route.path == "/docs/*rest" and info["params"] == {"rest": "guide/intro"}
    route, info = resolve(routes, "/docs")
    assert route.path == "/docs/*rest" and info["params"] == {"rest": ""}
    assert resolve(routes, "/u")[1]["params"] == {"id": ""}
    assert resolve(routes, "/u/5")[1]["params"] == {"id": "5"}
    assert resolve(routes, "/anything/else")[1]["params"] == {"wildcard": "anything/else"}
    with pytest.raises(ValueError, match="last segment"):
        resolve([RouteSpec("/*a/b")], "/x/b")


def test_resolve_prefers_literals_then_parameters_then_catch_alls():
    routes = [RouteSpec("*404"), RouteSpec("/users/:id"), RouteSpec("/users/new")]
    assert resolve(routes, "/users/new")[0].path == "/users/new"
    assert resolve(routes, "/users/7")[0].path == "/users/:id"
    assert resolve(routes, "/nope")[0].path == "*404"


def test_resolve_strips_the_base_path():
    routes = [RouteSpec("/docs/*")]
    route, info = resolve(routes, "/app/docs/guide", base_path="/app")
    assert info["params"] == {"wildcard": "guide"}
    assert resolve(routes, "/x/docs/guide", base_path="/app") is None


def test_route_props_fields():
    fields = RouteProps._wyb_fields
    assert {"params", "search", "data", "children"} <= set(fields)
    assert not any(fields[name].required for name in fields)


def test_a_hash_change_alone_doesnt_preload_again():
    calls: list[str] = []

    def preload(args: PreloadArgs) -> str:
        calls.append(args.location)
        return "data"

    @component
    def Page(props: RouteProps):
        return html(t"<p>{props.data}</p>")

    router = create_router([Route("/", Home), Route("/users/:id", Page, preload=preload)])
    with render(router()) as screen:
        go("/users/7")
        go("/users/7#bio")
        go("/users/7#photos")
        assert calls == ["/users/7"]
        assert screen.text() == "data"
        go("/users/7?tab=b")
        assert calls == ["/users/7", "/users/7?tab=b"]
