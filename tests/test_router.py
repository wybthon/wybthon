import pytest
from conftest import collect_texts

from wybthon import html
from wybthon.component import component
from wybthon.reactivity import create_signal, flush, untrack
from wybthon.router import (
    Link,
    Outlet,
    Route,
    RouteProps,
    Router,
    RouteSpec,
    current_path,
    navigate,
    resolve,
    use_base_path,
    use_hash,
    use_params,
    use_query,
)


def texts(node):
    return [t for t in collect_texts(node) if t]


def find(node, tag):
    out = []
    if getattr(node, "tag", None) == tag:
        out.append(node)
    for child in getattr(node, "childNodes", []):
        out.extend(find(child, tag))
    return out


@pytest.fixture(autouse=True)
def reset_path():
    navigate("/")
    flush()
    yield
    navigate("/")
    flush()


@component
def Home():
    return html(t"<h1>Home</h1>")


@component
def User(props: RouteProps):
    return html(t"<h1>User {props.params['id']} tab={props.query.get('tab', '-')}</h1>")


@component
def NotFound():
    return html(t"<p>nope</p>")


def test_router_renders_matched_component(wyb, root_element):
    root = wyb["reconciler"].render(Router([Route("/", Home), Route("/users/:id", User)]), root_element)
    assert texts(root_element.element) == ["Home"]
    root.dispose()


def test_navigate_swaps_content_and_exposes_params(wyb, root_element):
    root = wyb["reconciler"].render(Router([Route("/", Home), Route("/users/:id", User)]), root_element)
    navigate("/users/42")
    flush()
    assert current_path() == "/users/42"
    assert texts(root_element.element) == ["User ", "42", " tab=", "-"]
    navigate("/")
    flush()
    assert texts(root_element.element) == ["Home"]
    root.dispose()


def test_param_change_updates_props_without_remount(wyb, root_element):
    mounted = []

    @component
    def Tracked(props: RouteProps):
        mounted.append(1)
        return html(t"<span>{props.params['id']}</span>")

    root = wyb["reconciler"].render(Router([Route("/users/:id", Tracked)]), root_element)
    navigate("/users/1")
    flush()
    assert texts(root_element.element) == ["1"]
    navigate("/users/2")
    flush()
    assert texts(root_element.element) == ["2"]
    assert mounted == [1]
    root.dispose()


def test_query_string_is_parsed_into_query_prop(wyb, root_element):
    root = wyb["reconciler"].render(Router([Route("/users/:id", User)]), root_element)
    navigate("/users/7?tab=posts&x=a%20b")
    flush()
    assert texts(root_element.element) == ["User ", "7", " tab=", "posts"]
    root.dispose()


def test_use_params_and_use_query_accessors(wyb, root_element):
    @component
    def Page():
        params = use_params()
        query = use_query()
        return html(t"<p>{f'{params().get("slug")}|{query().get("a", "")}|{use_base_path()}'}</p>")

    root = wyb["reconciler"].render(Router([Route("/posts/:slug", Page)]), root_element)
    navigate("/posts/hello?a=1")
    flush()
    assert texts(root_element.element) == ["hello|1|"]
    root.dispose()


def test_use_params_and_use_query_outside_router(wyb, root_element):
    seen = {}

    @component
    def Lonely():
        seen["params"] = use_params()()
        seen["query"] = use_query()()
        seen["base"] = use_base_path()
        return html(t"<p>x</p>")

    root = wyb["reconciler"].render(Lonely(), root_element)
    assert seen == {"params": {}, "query": {}, "base": ""}
    root.dispose()


def test_nested_routes_match_children(wyb, root_element):
    @component
    def About():
        return html(t"<div><h1>About</h1>{Outlet()}</div>")

    @component
    def Team(props: RouteProps):
        return html(t"<h1>Team {props.params.get('name', '')}</h1>")

    routes = [Route("/about", About, children=[Route("team/:name", Team)])]
    root = wyb["reconciler"].render(Router(routes), root_element)
    navigate("/about")
    flush()
    assert texts(root_element.element) == ["About"]
    navigate("/about/team/core")
    flush()
    assert texts(root_element.element) == ["About", "Team ", "core"]
    root.dispose()


def test_not_found_fallback_and_default(wyb, root_element):
    root = wyb["reconciler"].render(Router([Route("/", Home)], not_found=NotFound), root_element)
    navigate("/missing")
    flush()
    assert texts(root_element.element) == ["nope"]
    root.dispose()

    root = wyb["reconciler"].render(Router([Route("/", Home)]), root_element)
    navigate("/missing-too")
    flush()
    assert texts(root_element.element) == ["Not Found"]
    root.dispose()


def test_base_path_prefixes_links_and_matching(wyb, root_element):
    @component
    def Shell():
        return html(t"""<div>
            {Link("Users", href="/users")}{Link("Ext", href="https://example.com/x")}<span>{use_base_path()}</span>
        </div>""")

    routes = [Route("/", Shell), Route("/users", User)]
    root = wyb["reconciler"].render(Router(routes, base_path="/app"), root_element)
    navigate("/app")
    flush()
    anchors = find(root_element.element, "a")
    assert anchors[0].attributes["href"] == "/app/users"
    assert anchors[1].attributes["href"] == "https://example.com/x"
    assert texts(root_element.element)[-1] == "/app"
    navigate("/app/users")
    flush()
    assert texts(root_element.element)[:1] == ["User "]
    navigate("/other/users")
    flush()
    assert texts(root_element.element) == ["Not Found"]
    root.dispose()


def test_link_renders_anchor_with_active_class(wyb, root_element):
    view = html(t"""<nav>
        {Link("Home", href="/", end=True, class_="lnk")}
        {Link("Users", href="/users")}
        {Link("Exact users", href="/users", end=True)}
        {Link("Quiet", href="/users", active_class=None)}
        {Link("Custom", href="/users", active_class="on")}
    </nav>""")
    root = wyb["reconciler"].render(view, root_element)
    anchors = find(root_element.element, "a")
    assert [a.attributes["href"] for a in anchors] == ["/", "/users", "/users", "/users", "/users"]
    assert anchors[0].attributes["class"] == "lnk active"
    assert "class" not in anchors[1].attributes

    navigate("/users/5")
    flush()
    assert anchors[0].attributes["class"] == "lnk"
    assert anchors[1].attributes["class"] == "active"
    assert "class" not in anchors[2].attributes  # end=True needs an exact match
    assert "class" not in anchors[3].attributes
    assert anchors[4].attributes["class"] == "on"

    navigate("/users")
    flush()
    assert anchors[2].attributes["class"] == "active"
    root.dispose()


def test_link_click_navigates_and_prevents_default(wyb, root_element):
    events = []
    root = wyb["reconciler"].render(
        Link("Go", href="/users/9", on_click=lambda evt: events.append(evt), data_testid="go"),
        root_element,
    )
    anchor = find(root_element.element, "a")[0]
    assert anchor.attributes["data-testid"] == "go"
    wyb["kernel"]._backend.dispatch("click", anchor)
    assert current_path() == "/users/9"
    assert len(events) == 1
    assert events[0]._default_prevented is True
    assert anchor.attributes["class"] == "active"
    root.dispose()


def test_modifier_click_is_passed_through_to_browser(wyb, root_element):
    events = []
    root = wyb["reconciler"].render(Link("Go", href="/users/9", on_click=lambda evt: events.append(evt)), root_element)
    anchor = find(root_element.element, "a")[0]
    wyb["kernel"]._backend.dispatch("click", anchor, payload={"metaKey": True})
    assert current_path() == "/"
    assert events[0]._default_prevented is False
    wyb["kernel"]._backend.dispatch("click", anchor, payload={"button": 1})
    assert current_path() == "/"
    root.dispose()


def test_link_replace_navigates_without_browser(wyb, root_element):
    root = wyb["reconciler"].render(Link("Go", href="/replaced", replace=True), root_element)
    anchor = find(root_element.element, "a")[0]
    wyb["kernel"]._backend.dispatch("click", anchor)
    assert current_path() == "/replaced"
    navigate("/again", replace=True)
    flush()
    assert current_path() == "/again"
    root.dispose()


def test_router_accepts_accessor_routes(wyb, root_element):
    routes, set_routes = create_signal([Route("/", Home)])
    root = wyb["reconciler"].render(Router(routes, not_found=NotFound), root_element)
    navigate("/users/3")
    flush()
    assert texts(root_element.element) == ["nope"]
    set_routes([Route("/", Home), Route("/users/:id", User)])
    flush()
    assert texts(root_element.element) == ["User ", "3", " tab=", "-"]
    root.dispose()


def test_nested_layout_persists_and_query_hash_decode(wyb, root_element):
    mounted = []

    @component
    def Layout():
        mounted.append("layout")
        return html(t"<div>{Outlet()}</div>")

    @component
    def Child():
        params, query, fragment = use_params(), use_query(), use_hash()
        return html(t"<p>{f'{params()["id"]}:{query().get_all("tag")}:{fragment()}'}</p>")

    routes = [Route("/parent", Layout, children=[Route(":id", Child), Route("", Home)])]
    root = wyb["reconciler"].render(Router(routes), root_element)
    navigate("/parent/hello%20world?tag=a&tag=b#some%20section")
    flush()
    assert texts(root_element.element) == ["hello world:['a', 'b']:some section"]
    navigate("/parent/")
    flush()
    assert texts(root_element.element) == ["Home"]
    assert mounted == ["layout"]
    root.dispose()


def test_route_preload_is_shared_and_owned(wyb, root_element):
    import asyncio

    from wybthon import Loading
    from wybthon.router import preload

    async def main():
        gate = asyncio.Event()
        called, closed = [], []

        async def load(params):
            called.append(params["id"])
            try:
                await gate.wait()
            finally:
                closed.append(params["id"])

        @component
        def Start():
            return Link("Warm", href="/users/1", on_click=lambda e: preload("/users/1"))

        routes = [Route("/", Start), Route("/users/:id", User, preload=load)]
        root = wyb["reconciler"].render(Loading(lambda: Router(routes), fallback="wait"), root_element)
        anchor = find(root_element.element, "a")[0]
        wyb["kernel"]._backend.dispatch("mouseenter", anchor)
        await asyncio.sleep(0)
        assert called == ["1"]
        navigate("/users/1")
        flush()
        await asyncio.sleep(0)
        assert called == ["1"]
        gate.set()
        for _ in range(8):
            await asyncio.sleep(0)
            flush()
        assert texts(root_element.element) == ["User ", "1", " tab=", "-"]
        gate.clear()
        navigate("/users/2")
        flush()
        await asyncio.sleep(0)
        root.dispose()
        for _ in range(4):
            await asyncio.sleep(0)
        assert closed == ["1", "2"]

    asyncio.run(main())


def test_async_link_callback_can_prevent_navigation_and_is_owned(wyb, root_element):
    import asyncio

    async def main():
        events = []
        gate = asyncio.Event()

        async def clicked(event):
            event.prevent_default()
            events.append("started")
            try:
                await gate.wait()
            finally:
                events.append("closed")

        root = wyb["reconciler"].render(Link("Go", href="/elsewhere", on_click=clicked), root_element)
        wyb["kernel"]._backend.dispatch("click", find(root_element.element, "a")[0])
        assert current_path() == "/"
        assert events == ["started"]
        root.dispose()
        for _ in range(3):
            await asyncio.sleep(0)
        assert events == ["started", "closed"]

    asyncio.run(main())


# ---------------------------------------------------------------------------
# Router, Link, and Outlet in templates
# ---------------------------------------------------------------------------


def test_routed_component_reads_params_and_query_as_plain_values(wyb, root_element):
    seen: list[tuple[dict, dict]] = []

    @component
    def Probe(props: RouteProps):
        seen.append((untrack(lambda: props.params), untrack(lambda: dict(props.query))))
        return html(t"<p>{props.params['id']}</p>")

    root = wyb["reconciler"].render(html(t"<main>{Router([Route('/items/:id', Probe)])}</main>"), root_element)
    navigate("/items/5?sort=asc")
    flush()
    assert seen == [({"id": "5"}, {"sort": "asc"})]
    assert texts(root_element.element) == ["5"]
    navigate("/items/6")
    flush()
    assert texts(root_element.element) == ["6"]
    assert len(seen) == 1
    root.dispose()


def test_router_route_table_in_a_template_is_evaluated_once(wyb, root_element):
    # The route list is a dynamic expression (it contains calls); the router
    # evaluates it once, so its `Route`s keep their identity and a matched
    # route isn't remounted on navigation.
    mounted: list[str] = []

    @component
    def Page(props: RouteProps):
        mounted.append(untrack(lambda: props.params)["id"])
        return html(t"<p>page {props.params['id']}</p>")

    view = html(t"<main>{Router([Route('/', Home), Route('/p/:id', Page)], not_found=NotFound)}</main>")
    root = wyb["reconciler"].render(view, root_element)
    assert texts(root_element.element) == ["Home"]
    navigate("/p/1")
    flush()
    navigate("/p/2")
    flush()
    assert texts(root_element.element) == ["page ", "2"]
    assert mounted == ["1"]
    navigate("/nowhere")
    flush()
    assert texts(root_element.element) == ["nope"]
    root.dispose()


def test_router_base_path_expression_in_a_template(wyb, root_element):
    prefix, _ = create_signal("/app")
    routes = [Route("/", Home)]
    root = wyb["reconciler"].render(html(t"<main>{Router(routes, base_path=prefix())}</main>"), root_element)
    navigate("/app")
    flush()
    assert texts(root_element.element) == ["Home"]
    navigate("/")
    flush()
    assert texts(root_element.element) == ["Not Found"]
    root.dispose()


def test_link_href_expression_in_a_template_updates(wyb, root_element):
    # `href=f"/users/{uid()}"` is dynamic: the link receives a getter.
    uid, set_uid = create_signal(1)
    root = wyb["reconciler"].render(html(t"<nav>{Link('User', href=f'/users/{uid()}')}</nav>"), root_element)
    anchor = find(root_element.element, "a")[0]
    assert anchor.attributes["href"] == "/users/1"
    set_uid(2)
    flush()
    assert anchor.attributes["href"] == "/users/2"
    wyb["kernel"]._backend.dispatch("click", anchor)
    assert current_path() == "/users/2"
    root.dispose()


def test_link_children_and_attributes_from_a_template(wyb, root_element):
    count, set_count = create_signal(0)
    view = html(t"<nav>{Link(html(t'<b>Inbox {count()}</b>'), href='/inbox', aria_label='Inbox')}</nav>")
    root = wyb["reconciler"].render(view, root_element)
    anchor = find(root_element.element, "a")[0]
    assert anchor.attributes["aria-label"] == "Inbox"
    assert texts(anchor) == ["Inbox ", "0"]
    set_count(3)
    flush()
    assert texts(anchor) == ["Inbox ", "3"]
    root.dispose()


def test_outlet_in_a_template_renders_the_child_route(wyb, root_element):
    @component
    def Shell():
        return html(t"<div><header>top</header>{Outlet()}<footer>bottom</footer></div>")

    @component
    def Leaf(props: RouteProps):
        return html(t"<p>leaf {props.params['name']}</p>")

    routes = [Route("/s", Shell, children=[Route(":name", Leaf)])]
    root = wyb["reconciler"].render(html(t"<main>{Router(routes)}</main>"), root_element)
    navigate("/s")
    flush()
    assert texts(root_element.element) == ["top", "bottom"]
    navigate("/s/x")
    flush()
    assert texts(root_element.element) == ["top", "leaf ", "x", "bottom"]
    navigate("/s/y")
    flush()
    assert texts(root_element.element) == ["top", "leaf ", "y", "bottom"]
    root.dispose()


# ---------------------------------------------------------------------------
# Path resolution (formerly ``wybthon.router_core``): no browser needed
# ---------------------------------------------------------------------------


def test_resolve_basic_match():
    routes = [RouteSpec("/"), RouteSpec("/about")]
    route, info = resolve(routes, "/about")
    assert route.path == "/about"
    assert info["params"] == {}


def test_resolve_params():
    route, info = resolve([RouteSpec("/users/:id")], "/users/42")
    assert route.path == "/users/:id"
    assert info["params"]["id"] == "42"


def test_resolve_nested_children_match():
    route, info = resolve([RouteSpec("/about", children=[RouteSpec("team")])], "/about/team")
    assert route.path == "team"
    assert info["params"] == {}
    assert [r.path for r in info["matches"]] == ["/about", "team"]


def test_resolve_wildcard_match_and_empty_tail():
    routes = [RouteSpec("/docs/*")]
    route, info = resolve(routes, "/docs/guide/intro")
    assert route.path == "/docs/*"
    assert info["params"]["wildcard"] == "guide/intro"

    route2, info2 = resolve(routes, "/docs")
    assert route2.path == "/docs/*"
    # The optional tail is empty when matching just "/docs".
    assert info2["params"].get("wildcard", "") in ("", None)


def test_resolve_base_path_stripping():
    routes = [RouteSpec("/about"), RouteSpec("/docs/*")]
    route, info = resolve(routes, "/app/docs/guide", base_path="/app")
    assert route.path == "/docs/*"
    assert info["params"]["wildcard"] == "guide"
    # A base path mismatch doesn't match.
    assert resolve(routes, "/x/docs/guide", base_path="/app") is None


def test_resolve_prefers_static_segments_over_params():
    routes = [RouteSpec("/users/:id"), RouteSpec("/users/new")]
    route, info = resolve(routes, "/users/new")
    assert route.path == "/users/new"
    assert info["params"] == {}


def test_resolve_accepts_any_object_with_path():
    from dataclasses import dataclass

    @dataclass
    class R:
        path: str
        children: list | None = None

    route, _info = resolve([R("/a", children=[R(":x")])], "/a/b?q=1")
    assert route.path == ":x"


def test_route_props_defaults():
    fields = RouteProps._wyb_fields
    assert {"params", "query"} <= set(fields)
    assert not any(fields[name].required for name in ("params", "query"))
