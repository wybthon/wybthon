import pytest
from conftest import collect_texts

from wybthon.component import component
from wybthon.html import div, h1, nav, p, span
from wybthon.reactivity import Prop, Props, flush
from wybthon.router import Link, Outlet, Route, Router, current_path, navigate, use_base_path, use_params, use_query


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
    return h1("Home")


@component
def User(params: Prop[dict], query: Prop[dict]):
    return h1("User ", lambda: params()["id"], " tab=", lambda: query().get("tab", "-"))


@component
def NotFound():
    return p("nope")


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
    def Tracked(params: Prop[dict], query: Prop[dict]):
        mounted.append(1)
        return span(lambda: params()["id"])

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
        return p(lambda: f"{params().get('slug')}|{query().get('a', '')}|{use_base_path()}")

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
        return p("x")

    root = wyb["reconciler"].render(Lonely(), root_element)
    assert seen == {"params": {}, "query": {}, "base": ""}
    root.dispose()


def test_nested_routes_match_children(wyb, root_element):
    @component
    def About():
        return div(h1("About"), Outlet())

    @component
    def Team(props: Props):
        return h1("Team ", lambda: props.params().get("name", ""))

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
        return div(Link("Users", href="/users"), Link("Ext", href="https://example.com/x"), span(use_base_path()))

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
    root = wyb["reconciler"].render(
        nav(
            Link("Home", href="/", end=True, class_="lnk"),
            Link("Users", href="/users"),
            Link("Exact users", href="/users", end=True),
            Link("Quiet", href="/users", active_class=None),
            Link("Custom", href="/users", active_class="on"),
        ),
        root_element,
    )
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
    from wybthon.reactivity import create_signal

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
    from wybthon import use_hash

    mounted = []

    @component
    def Layout():
        mounted.append("layout")
        return div(Outlet())

    @component
    def Child():
        params, query, fragment = use_params(), use_query(), use_hash()
        return p(lambda: f"{params()['id']}:{query().get_all('tag')}:{fragment()}")

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

    from wybthon import Loading, preload

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
