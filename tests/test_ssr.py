"""Server rendering, streaming, and hydration (RFC 0001, engine v2 in RFC 0002)."""

import asyncio
import json
import re
from typing import Any, Literal

import pytest
from conftest import StubNode, _StubHTMLParser, collect_texts

from wybthon import (
    Errored,
    For,
    Loading,
    Match,
    NoHydration,
    Portal,
    Props,
    Reveal,
    ServerError,
    Show,
    Switch,
    client_only,
    component,
    create_effect,
    create_memo,
    create_signal,
    create_unique_id,
    flush,
    html,
    hydrate,
    is_pending,
    is_server,
    lazy,
    on_settled,
    untrack,
)
from wybthon.dom import Element
from wybthon.router import Route, RouteProps, Router
from wybthon.server import RenderStream, render_to_stream, render_to_string


def render_async(view: Any, **options: Any) -> str:
    """Await `render_to_stream` for the complete HTML (the old `render_to_string_async`)."""

    async def main() -> str:
        return await render_to_stream(view, **options)

    return asyncio.run(main())


def texts(node: Any) -> list[str]:
    return [t for t in collect_texts(node) if t and not t.startswith(("wyb:", "/wyb:"))]


def visible(node: Any) -> str:
    """Concatenated visible text (comment markers excluded)."""
    out = []

    def walk(n: Any) -> None:
        if getattr(n, "_is_comment", False):
            return
        if getattr(n, "_is_text", False):
            out.append(n.nodeValue or "")
        for child in n.childNodes:
            walk(child)

    walk(node)
    return "".join(out)


def parse(html: str) -> StubNode:
    container = StubNode(tag="div")
    parser = _StubHTMLParser(container)
    parser.feed(html)
    parser.close()
    return container


def nodes(root: Any) -> list[Any]:
    out = [root]
    for child in root.childNodes:
        out.extend(nodes(child))
    return out


def find(root: Any, tag: str) -> Any:
    return next(n for n in nodes(root) if n.tag == tag)


class Hydrated:
    def __init__(self, wyb: dict[str, Any], html: str, view: Any) -> None:
        self.html = html
        self.container = parse(html)
        self.backend = wyb["kernel"].PythonBackend(_document())
        wyb["kernel"].set_backend(self.backend)
        self.before = nodes(self.container)
        self.queue: list[tuple[str, Any, Any]] = []

    def run(self, view: Any) -> Any:
        self.backend.queued_events = self.queue
        self.root = hydrate(view, Element(node=self.container))
        after = nodes(self.container)
        before_ids = {id(n) for n in self.before}
        self.created = [n for n in after if id(n) not in before_ids]
        self.created_elements = [n for n in self.created if n.tag is not None and not getattr(n, "_is_text", False)]
        return self.root

    @property
    def mismatches(self) -> int:
        return self.backend.hydration_mismatches


def _document() -> Any:
    import js

    return js.document


def hydrate_from(wyb: dict[str, Any], html: str, view: Any, queue: list[Any] | None = None) -> Hydrated:
    result = Hydrated(wyb, html, view)
    if queue:
        result.queue = queue
    result.run(view)
    return result


def strip_state(html: str) -> str:
    return re.sub(r'<script type="application/json" data-wyb-state>.*?</script>', "", html)


def state_of(html: str) -> dict[str, Any]:
    match = re.search(r"data-wyb-state>(.*?)</script>", html)
    assert match is not None
    return json.loads(match.group(1))


async def settle(rounds: int = 5) -> None:
    for _ in range(rounds):
        flush()
        await asyncio.sleep(0)
    flush()


# ---------------------------------------------------------------------------
# Static rendering and hydration
# ---------------------------------------------------------------------------


class CounterProps(Props):
    start: int = 0


@component
def Counter(props: CounterProps):
    count, set_count = create_signal(untrack(lambda: props.start))

    def increment(event: Any) -> None:
        set_count(lambda n: n + 1)

    return html(t'<div class="counter"><p>Count: {count}!</p><button onclick={increment}>+</button></div>')


def test_render_to_string_serializes_markup(wyb):
    out = render_to_string(html(t'<div class="a"><h1>{"Hi & <bye>"}</h1><input disabled value="x"></div>'))
    assert strip_state(out) == '<div class="a"><h1>Hi &amp; &lt;bye&gt;</h1><input disabled value="x"></div>'
    assert state_of(out) == {"v": {}}


def test_hydration_adopts_server_nodes_and_becomes_interactive(wyb):
    out = render_to_string(Counter(start=3))
    assert "<p>Count: 3!</p>" in out
    result = hydrate_from(wyb, out, Counter(start=3))
    assert result.mismatches == 0
    assert result.created_elements == []
    assert visible(result.container) == "Count: 3!+"
    result.backend.dispatch("click", find(result.container, "button"))
    flush()
    assert visible(result.container) == "Count: 4!+"


def test_hydration_splits_merged_text_and_restores_empty_text(wyb):
    @component
    def View():
        name, _ = create_signal("Ada")
        return html(t"<p>Hello, {name}{''}{(lambda: None)}!</p>")

    out = render_to_string(View())
    result = hydrate_from(wyb, out, View())
    assert result.mismatches == 0
    assert visible(result.container) == "Hello, Ada!"


def test_holes_fragments_and_nested_components_round_trip(wyb):
    class LeafProps(Props):
        text: str

    @component
    def Leaf(props: LeafProps):
        return html(t"<span>{props.text}</span>")

    @component
    def View():
        items, set_items = create_signal(["a", "b"])
        on, set_on = create_signal(True)

        def toggle(event: Any) -> None:
            set_on(lambda v: not v)

        def add(event: Any) -> None:
            set_items(lambda xs: [*xs, "c"])

        return html(t"""
          <div>
            {[Leaf(text=x) for x in items()]}
            {Leaf(text="yes") if on() else None}
            {(lambda: "text hole")}
            <button onclick={toggle}>toggle</button>
            <button onclick={add}>add</button>
          </div>
        """)

    out = render_to_string(View())
    result = hydrate_from(wyb, out, View())
    assert result.mismatches == 0
    assert result.created_elements == []
    assert texts(result.container) == ["a", "b", "yes", "text hole", "toggle", "add"]
    buttons = [n for n in nodes(result.container) if n.tag == "button"]
    result.backend.dispatch("click", buttons[0])
    result.backend.dispatch("click", buttons[1])
    flush()
    assert texts(result.container) == ["a", "b", "c", "text hole", "toggle", "add"]


def test_for_show_and_switch_round_trip(wyb):
    @component
    def View():
        items, set_items = create_signal([1, 2, 3])
        mode, set_mode = create_signal("a")

        def less(event: Any) -> None:
            set_items(lambda xs: xs[:1])

        def clear(event: Any) -> None:
            set_items([])

        return html(t"""
          <div>
            <ul>{For(items(), lambda item, index: html(t'<li class="row">{item}</li>'))}</ul>
            {Show(len(items()) > 2, html(t"<p>many</p>"), fallback=html(t"<p>few</p>"))}
            {Switch(Match(mode() == "a", html(t"<p>A</p>")), fallback=html(t"<p>other</p>"))}
            <button onclick={less}>less</button>
            <button onclick={clear}>clear</button>
          </div>
        """)

    out = render_to_string(View())
    result = hydrate_from(wyb, out, View())
    assert result.mismatches == 0
    assert result.created_elements == []
    assert texts(result.container) == ["1", "2", "3", "many", "A", "less", "clear"]
    less, clear = [n for n in nodes(result.container) if n.tag == "button"]
    result.backend.dispatch("click", less)
    flush()
    assert texts(result.container) == ["1", "few", "A", "less", "clear"]
    result.backend.dispatch("click", clear)
    flush()
    assert texts(result.container) == ["few", "A", "less", "clear"]


def test_unique_ids_match_between_server_and_client(wyb):
    @component
    def Field():
        field_id = create_unique_id()
        return html(t"<div><label for={field_id}>Name</label><input id={field_id}></div>")

    out = render_to_string(html(t"<div>{Field()}{Field()}</div>"))
    server_ids = re.findall(r'id="([^"]+)"', out)
    assert len(set(server_ids)) == 2
    result = hydrate_from(wyb, out, html(t"<div>{Field()}{Field()}</div>"))
    client_ids = [n.attributes["id"] for n in nodes(result.container) if n.tag == "input"]
    assert client_ids == server_ids


# ---------------------------------------------------------------------------
# Compiled dynamic expressions
# ---------------------------------------------------------------------------


class BadgeProps(Props):
    title: str
    count: int = 0


@component
def Badge(props: BadgeProps):
    return html(t"<span class={'many' if props.count > 2 else 'few'}>{props.title}: {props.count * 2}</span>")


def test_compiled_expressions_render_and_hydrate(wyb):
    label = "plain"

    @component
    def View():
        count, set_count = create_signal(2)
        user, set_user = create_signal({"name": "Ada"})

        def bump(event: Any) -> None:
            set_count(lambda n: n + 1)
            set_user({"name": "Grace"})

        return html(t"""
          <div class={"on" if count() > 2 else "off"}>
            <p>{count() * 2}</p>
            <p>{count() / 4:.2f}</p>
            <p>{label.upper()}</p>
            <{Badge} title={user()["name"]} count={count()} />
            <button onclick={bump}>bump</button>
          </div>
        """)

    out = render_to_string(View())
    assert strip_state(out) == (
        '<div class="off"><p>4</p><p>0.50</p><p>PLAIN</p><span class="few">Ada: 4</span><button>bump</button></div>'
    )
    result = hydrate_from(wyb, out, View())
    assert result.mismatches == 0
    assert result.created_elements == []
    root = next(n for n in nodes(result.container)[1:] if n.tag == "div")
    badge = find(result.container, "span")
    assert visible(result.container) == "40.50PLAINAda: 4bump"
    result.backend.dispatch("click", find(result.container, "button"))
    flush()
    assert visible(result.container) == "60.75PLAINGrace: 6bump"
    assert root.attributes["class"] == "on"
    assert badge.attributes["class"] == "many"


def test_compiled_expressions_stream_and_hydrate_inside_boundaries(wyb):
    gate = asyncio.Event()

    async def fetch_user() -> dict[str, Any]:
        await gate.wait()
        return {"name": "Ada", "posts": 3}

    @component
    def Profile():
        user = create_memo(lambda: fetch_user())
        return html(t"""
          <div class={"busy" if user()["posts"] > 2 else "idle"}>
            <{Badge} title={user()["name"]} count={user()["posts"]} />
            <p>{user()["posts"] * 10}</p>
          </div>
        """)

    def view():
        return html(t"<main><h1>{'header'.title()}</h1>{Loading(Profile(), fallback=html(t'<p>loading</p>'))}</main>")

    async def main() -> tuple[list[str], str]:
        chunks: list[str] = []
        async for chunk in render_to_stream(view):
            chunks.append(chunk)
            if len(chunks) == 1:
                gate.set()
        full = await render_to_stream(view)
        return chunks, full

    chunks, full = asyncio.run(main())
    assert "loading" in chunks[0] and "<h1>Header</h1>" in chunks[0] and "Ada" not in chunks[0]
    assert '<div class="busy"><span class="many">Ada: 6</span><p>30</p></div>' in chunks[1]
    assert apply_swaps(chunks[:-1]) == strip_state(full)
    result = hydrate_from(wyb, full, view())
    assert result.mismatches == 0
    assert result.created_elements == []
    assert visible(result.container) == "HeaderAda: 630"


# ---------------------------------------------------------------------------
# Server-mode behavior
# ---------------------------------------------------------------------------


def test_effects_and_on_settled_do_not_run_on_the_server(wyb):
    ran: list[str] = []
    seen: list[bool] = []

    @component
    def View():
        seen.append(is_server())
        create_effect(lambda: 1, lambda value: ran.append("effect"))
        on_settled(lambda: ran.append("settled"))
        return html(t"<p>x</p>")

    render_to_string(View())
    assert ran == []
    assert seen == [True]
    assert not is_server()


def test_portal_renders_nothing_on_the_server_and_mounts_after_hydration(wyb):
    target = StubNode(tag="aside")

    def view():
        return html(t"<div><p>main</p>{Portal(html(t'<p>in portal</p>'), mount=Element(node=target))}</div>")

    out = render_to_string(view)
    assert "in portal" not in out
    result = Hydrated(wyb, out, view)
    target_el = Element(node=target)
    result.run(html(t"<div><p>main</p>{Portal(html(t'<p>in portal</p>'), mount=target_el)}</div>"))
    assert result.mismatches == 0
    assert texts(target) == ["in portal"]
    assert texts(result.container) == ["main"]


def test_client_only_renders_fallback_until_hydrated(wyb):
    def view():
        return html(t"<div>{client_only(lambda: html(t'<p>browser</p>'), fallback=html(t'<p>server</p>'))}</div>")

    out = render_to_string(view)
    assert "server" in out and "browser" not in out
    result = hydrate_from(wyb, out, view())
    assert result.mismatches == 0
    assert texts(result.container) == ["browser"]


def test_router_renders_the_request_url(wyb):
    @component
    def Home():
        return html(t"<p>home</p>")

    @component
    def User(props: RouteProps):
        return html(t"<p>user {props.params['id']}</p>")

    def view():
        return Router([Route("/", Home), Route("/users/:id", User)])

    assert "user 7" in render_to_string(view, url="/users/7")
    assert "home" in render_to_string(view, url="/")


def test_render_rejects_view_mutation_between_passes(wyb):
    """A VNode view is copied for every pass, so it can be rendered repeatedly."""
    view = html(t"<div><p>one</p>{Counter(start=1)}</div>")
    first = render_to_string(view)
    second = render_to_string(view)
    assert first == second


# ---------------------------------------------------------------------------
# Async data
# ---------------------------------------------------------------------------


def make_app(calls: list[str], *, source: Literal["server", "hybrid", "client"] = "server", delay: float = 0.0):
    async def fetch_user(uid: int) -> dict[str, Any]:
        calls.append(f"user {uid}")
        await asyncio.sleep(delay)
        return {"id": uid, "name": f"User {uid}"}

    async def fetch_posts(uid: int) -> list[str]:
        calls.append(f"posts {uid}")
        await asyncio.sleep(delay)
        return [f"post {uid}.{i}" for i in range(2)]

    class UserProps(Props):
        uid: int

    @component
    def Posts(props: UserProps):
        posts = create_memo(lambda: fetch_posts(props.uid), ssr_source=source)
        return html(t"<ul>{For(posts, lambda post, i: html(t'<li>{post}</li>'))}</ul>")

    @component
    def Profile(props: UserProps):
        user = create_memo(lambda: fetch_user(props.uid), ssr_source=source)
        return html(t"""
          <div>
            <h1>{user()["name"]}</h1>
            <{Loading} fallback={html(t"<p>Loading posts</p>")}>
              <{Posts} uid={props.uid} />
            </{Loading}>
          </div>
        """)

    @component
    def App():
        uid, set_uid = create_signal(7)

        def next_user(event: Any) -> None:
            set_uid(lambda n: n + 1)

        return html(t"""
          <div>
            <button onclick={next_user}>next</button>
            {Loading(Profile(uid=uid()), fallback=html(t"<p>Loading profile</p>"))}
          </div>
        """)

    return App


def test_sync_render_shows_fallbacks_without_starting_async_work(wyb):
    calls: list[str] = []
    App = make_app(calls)
    out = render_to_string(App())
    assert "Loading profile" in out
    assert calls == []


def test_async_render_resolves_data_and_hydration_reuses_it(wyb):
    calls: list[str] = []
    App = make_app(calls)
    out = render_async(App())
    assert "User 7" in out and "post 7.1" in out and "Loading" not in strip_state(out)
    assert sorted(calls) == ["posts 7", "user 7"]
    assert len(state_of(out)["v"]) == 2

    async def main() -> None:
        calls.clear()
        result = hydrate_from(wyb, out, App())
        assert result.mismatches == 0
        assert result.created_elements == []
        await settle()
        assert calls == []
        assert texts(result.container) == ["next", "User 7", "post 7.0", "post 7.1"]
        # Later changes load normally, as a transition.
        result.backend.dispatch("click", find(result.container, "button"))
        await settle()
        for _ in range(20):
            await asyncio.sleep(0)
            flush()
        assert "User 8" in texts(result.container)
        assert "user 8" in calls

    asyncio.run(main())


def test_waterfalls_resolve_across_passes(wyb):
    order: list[str] = []

    async def first() -> int:
        order.append("first")
        await asyncio.sleep(0)
        return 2

    async def second(n: int) -> str:
        order.append("second")
        await asyncio.sleep(0)
        return f"value {n}"

    class InnerProps(Props):
        n: int

    @component
    def Inner(props: InnerProps):
        text = create_memo(lambda: second(props.n))
        return html(t"<p>{text}</p>")

    @component
    def Outer():
        n = create_memo(first)
        return html(t"<div>{Inner(n=n())}</div>")

    out = render_async(Loading(Outer(), fallback="wait"))
    assert "value 2" in out
    assert order.count("first") == 1 and order.count("second") == 1


def test_async_errors_are_serialized_and_raised_on_the_client(wyb):
    async def fail() -> str:
        raise ValueError("backend down")

    @component
    def Data():
        value = create_memo(lambda: fail())
        return html(t"<p>{value()}</p>")

    def view():
        return Errored(Loading(Data(), fallback="wait"), fallback=lambda err, reset: html(t"<p>error: {err()}</p>"))

    out = render_async(view)
    assert "error: backend down" in out
    assert "ValueError" in json.dumps(state_of(out))
    seen: list[BaseException] = []

    def client_view():
        return Errored(
            Loading(Data(), fallback="wait"),
            fallback=lambda err, reset: (seen.append(err()), html(t"<p>error: {err()}</p>"))[1],
        )

    result = hydrate_from(wyb, out, client_view())
    assert result.mismatches == 0
    assert isinstance(seen[0], ServerError)
    assert seen[0].type_name == "ValueError"


def test_client_source_loads_after_hydration(wyb):
    calls: list[str] = []
    App = make_app(calls, source="client")
    out = render_async(App())
    assert calls == []
    assert "Loading profile" in out

    async def main() -> None:
        result = hydrate_from(wyb, out, App())
        await settle(20)
        assert "User 7" in texts(result.container)
        assert "user 7" in calls

    asyncio.run(main())


def test_hybrid_source_keeps_the_server_value_while_it_refreshes(wyb):
    calls: list[str] = []
    App = make_app(calls, source="hybrid")
    out = render_async(App())

    async def main() -> None:
        calls.clear()
        result = hydrate_from(wyb, out, App())
        assert result.mismatches == 0
        assert "User 7" in texts(result.container)
        await settle(20)
        assert "user 7" in calls
        assert "User 7" in texts(result.container)

    asyncio.run(main())


def test_async_def_memos_rerun_quietly_after_hydration(wyb):
    calls: list[int] = []

    @component
    def Data():
        async def load() -> str:
            calls.append(1)
            await asyncio.sleep(0)
            return "loaded"

        value = create_memo(load)
        return html(t"<p>{value}{' (refreshing)' if is_pending(value) else ''}</p>")

    def view():
        return Loading(Data(), fallback="wait")

    out = render_async(view)

    async def main() -> None:
        calls.clear()
        result = hydrate_from(wyb, out, view())
        assert result.mismatches == 0
        assert visible(result.container) == "loaded"
        await settle(10)
        assert calls == [1]
        assert visible(result.container) == "loaded"

    asyncio.run(main())


def test_non_json_values_are_skipped_with_a_warning(wyb, capsys):
    class Opaque:
        def __str__(self) -> str:
            return "opaque"

    async def load() -> Opaque:
        return Opaque()

    @component
    def Data():
        value = create_memo(lambda: load())
        return html(t"<p>{str(value())}</p>")

    out = render_async(Loading(Data(), fallback="wait"))
    assert "opaque" in out
    assert state_of(out) == {"v": {}}
    assert "isn't JSON-compatible" in capsys.readouterr().err


def test_sync_render_with_async_data_heals_during_hydration(wyb):
    calls: list[str] = []
    App = make_app(calls)
    out = render_to_string(App())

    async def main() -> None:
        result = hydrate_from(wyb, out, App())
        await settle(30)
        assert texts(result.container) == ["next", "User 7", "post 7.0", "post 7.1"]

    asyncio.run(main())


def test_timeout_renders_fallbacks_for_slow_data(wyb):
    async def slow() -> str:
        await asyncio.sleep(10)
        return "late"

    @component
    def Data():
        value = create_memo(lambda: slow())
        return html(t"<p>{value}</p>")

    out = render_async(Loading(Data(), fallback="waiting"), timeout=0.05)
    assert "waiting" in out and "late" not in out


def test_lazy_components_render_on_the_server(wyb):
    @component
    def Page():
        return html(t"<p>lazy page</p>")

    Lazy = lazy(lambda: Page)

    def view():
        return html(t"<div>{Loading(Lazy(), fallback='wait')}{Counter(start=5)}</div>")

    out = render_async(view)
    assert "lazy page" in out and "Count: 5!" in out
    result = hydrate_from(wyb, out, view())
    assert result.mismatches == 0
    assert texts(result.container) == ["lazy page", "Count: ", "5", "!", "+"]


# ---------------------------------------------------------------------------
# Streaming
# ---------------------------------------------------------------------------


def apply_swaps(chunks: list[str]) -> str:
    """Apply streamed boundary swaps to the shell, as the inline script does."""
    document = chunks[0]
    for chunk in chunks[1:]:
        for key, content in re.findall(r'<template id="wyb-t([0-9a-f]+)">(.*?)</template>', chunk, re.S):
            start, end = f"<!--wyb:b{key}-->", f"<!--/wyb:b{key}-->"
            head, rest = document.split(start, 1)
            _old, tail = rest.split(end, 1)
            document = head + start + content + end + tail
    return document


def test_stream_sends_shell_then_boundaries_then_state(wyb):
    async def main() -> list[str]:
        gates = {"profile": asyncio.Event(), "posts": asyncio.Event()}

        async def fetch_user() -> str:
            await gates["profile"].wait()
            return "Ada"

        async def fetch_posts() -> list[str]:
            await gates["posts"].wait()
            return ["one", "two"]

        @component
        def Posts():
            posts = create_memo(lambda: fetch_posts())
            return html(t"<ul>{For(posts(), lambda post, i: html(t'<li>{post}</li>'))}</ul>")

        @component
        def Profile():
            user = create_memo(lambda: fetch_user())
            return html(t"<div><h1>{user}</h1>{Loading(Posts(), fallback=html(t'<p>posts...</p>'))}</div>")

        def view():
            return html(t"<div><p>header</p>{Loading(Profile(), fallback=html(t'<p>profile...</p>'))}</div>")

        chunks: list[str] = []
        async for chunk in render_to_stream(view):
            chunks.append(chunk)
            if len(chunks) == 1:
                gates["profile"].set()
            elif len(chunks) == 2:
                gates["posts"].set()
        return chunks

    chunks = asyncio.run(main())
    assert len(chunks) == 4
    assert "profile..." in chunks[0] and "header" in chunks[0]
    assert "__wybSwap" in chunks[1] and "Ada" in chunks[1] and "posts..." in chunks[1]
    assert "two" in chunks[2] and "__wybSwap(" in chunks[2] and "function __wybSwap" not in chunks[2]
    assert chunks[-1].startswith('<script type="application/json" data-wyb-state>')
    assembled = apply_swaps(chunks[:-1])
    assert "Ada" in assembled and "two" in assembled
    assert "profile..." not in assembled and "posts..." not in assembled


def test_streamed_document_matches_the_async_render(wyb):
    calls: list[str] = []
    App = make_app(calls)

    async def main() -> tuple[list[str], str]:
        chunks = [chunk async for chunk in render_to_stream(App())]
        full = await render_to_stream(App())
        return chunks, full

    chunks, full = asyncio.run(main())
    assert apply_swaps(chunks[:-1]) == strip_state(full)


def test_reveal_orders_streamed_boundaries(wyb):
    async def main() -> list[str]:
        gates = [asyncio.Event(), asyncio.Event()]

        def panel(index: int):
            async def load() -> str:
                await gates[index].wait()
                return f"panel {index}"

            @component
            def Panel():
                value = create_memo(lambda: load())
                return html(t"<p>{value()}</p>")

            return Panel

        first, second = panel(0), panel(1)

        def view():
            return html(t"""
              <{Reveal} order="sequential">
                {Loading(first(), fallback="wait 0")}
                {Loading(second(), fallback="wait 1")}
              </{Reveal}>
            """)

        chunks: list[str] = []
        async for chunk in render_to_stream(view):
            chunks.append(chunk)
            if len(chunks) == 1:
                gates[1].set()
                await asyncio.sleep(0.01)
                gates[0].set()
        return chunks

    chunks = asyncio.run(main())
    assembled = apply_swaps(chunks[:-1])
    assert "panel 0" in assembled and "panel 1" in assembled


# ---------------------------------------------------------------------------
# Tolerant claiming and replay
# ---------------------------------------------------------------------------


def test_mismatched_html_is_repaired(wyb):
    out = '<div><span>stale</span><p>extra</p></div><script type="application/json" data-wyb-state>{"v":{}}</script>'
    result = hydrate_from(wyb, out, html(t"<div><p>fresh</p><button>b</button></div>"))
    assert result.mismatches > 0
    assert [n.tag for n in nodes(result.container)[1:] if n.tag] == ["div", "p", "button"]
    assert texts(result.container) == ["fresh", "b"]


def test_loading_end_marker_resynchronizes(wyb):
    calls: list[str] = []
    App = make_app(calls)
    out = render_async(App())
    # Corrupt the boundary's content: the end marker must stop the damage.
    broken = out.replace("<h1>User 7</h1>", "<h2>Wrong</h2><h3>More</h3>")

    async def main() -> None:
        result = hydrate_from(wyb, broken, App())
        await settle()
        assert result.mismatches > 0
        assert texts(result.container) == ["next", "User 7", "post 7.0", "post 7.1"]

    asyncio.run(main())


def test_input_before_hydration_is_replayed(wyb):
    out = render_to_string(Counter(start=0))
    container_html = parse(out)
    button_node = find(container_html, "button")
    result = Hydrated(wyb, out, Counter())
    result.container = container_html
    result.before = nodes(container_html)
    result.queue = [("click", button_node, None), ("click", button_node, None)]
    result.run(Counter(start=0))
    assert visible(result.container) == "Count: 2!+"


def test_state_script_is_consumed(wyb):
    out = render_to_string(html(t"<p>x</p>"))
    result = hydrate_from(wyb, out, html(t"<p>x</p>"))
    assert not any(n.tag == "script" for n in nodes(result.container))


@pytest.mark.parametrize("route", ["/", "/about"])
def test_render_to_string_accepts_factories(wyb, route):
    @component
    def Home():
        return html(t"<p>home</p>")

    @component
    def About():
        return html(t"<p>about</p>")

    out = render_to_string(lambda: Router([Route("/", Home), Route("/about", About)]), url=route)
    assert ("about" if route == "/about" else "home") in out


# ---------------------------------------------------------------------------
# render_to_stream: iterate or await, once
# ---------------------------------------------------------------------------


def test_render_to_stream_returns_a_single_use_stream(wyb):
    calls: list[str] = []
    App = make_app(calls)

    async def main() -> None:
        stream = render_to_stream(App())
        assert isinstance(stream, RenderStream)
        full = await stream
        assert "User 7" in full and "post 7.1" in full
        assert full.endswith("</script>") and "data-wyb-state" in full
        with pytest.raises(RuntimeError, match="only once"):
            await stream
        with pytest.raises(RuntimeError, match="only once"):
            stream.__aiter__()

        iterated = render_to_stream(App())
        chunks = [chunk async for chunk in iterated]
        assert len(chunks) >= 2
        assert chunks[-1].startswith('<script type="application/json" data-wyb-state>')
        with pytest.raises(RuntimeError, match="only once"):
            await iterated
        assert apply_swaps(chunks[:-1]) == strip_state(full)

    asyncio.run(main())


def test_render_to_stream_without_async_data_streams_shell_and_state(wyb):
    async def main() -> list[str]:
        return [chunk async for chunk in render_to_stream(Counter(start=2), url="/x")]

    chunks = asyncio.run(main())
    assert chunks[0] == strip_state(render_to_string(Counter(start=2)))
    assert chunks[-1] == '<script type="application/json" data-wyb-state>{"v":{}}</script>'


def test_awaited_stream_matches_sync_render_without_async_data(wyb):
    assert render_async(Counter(start=4)) == render_to_string(Counter(start=4))


def test_server_exports():
    import wybthon.server as server

    assert set(server.__all__) == {"render_to_string", "render_to_stream", "RenderStream"}


# ---------------------------------------------------------------------------
# NoHydration
# ---------------------------------------------------------------------------


def test_no_hydration_renders_static_markup_inside_markers(wyb):
    out = render_to_string(
        html(t"<div>{NoHydration(html(t'<p>legal</p>'), html(t'<span>text</span>'))}<p>after</p></div>")
    )
    assert strip_state(out) == "<div><!--wyb:nh--><p>legal</p><span>text</span><!--/wyb:nh--><p>after</p></div>"


def test_no_hydration_keeps_server_dom_static_while_hydrating(wyb):
    mounted: list[str] = []

    @component
    def Static():
        mounted.append("static")
        count, set_count = create_signal(0)

        def inc() -> None:
            set_count(lambda n: n + 1)

        return html(t"<div><p>static {count}</p><button onclick={inc}>inc</button></div>")

    @component
    def View():
        count, set_count = create_signal(0)

        def inc() -> None:
            set_count(lambda n: n + 1)

        return html(t"<div>{NoHydration(Static())}<p>live {count()}</p><button onclick={inc}>live</button></div>")

    out = render_to_string(View())
    assert mounted == ["static"]
    mounted.clear()
    result = hydrate_from(wyb, out, View())
    assert result.mismatches == 0
    assert result.created_elements == []
    # Nothing inside the region was mounted in the browser: its server
    # nodes (merged text included) are kept as they were.
    assert mounted == []
    static_p = next(n for n in nodes(result.container) if n.tag == "p")
    assert static_p in result.before
    assert [child.nodeValue for child in static_p.childNodes] == ["static 0"]
    assert visible(result.container) == "static 0inclive 0live"
    static_button, live_button = [n for n in nodes(result.container) if n.tag == "button"]
    result.backend.dispatch("click", static_button)
    result.backend.dispatch("click", live_button)
    flush()
    # The static region has no handlers and never updates; the rest is live.
    assert visible(result.container) == "static 0inclive 1live"


def test_no_hydration_renders_children_in_a_client_only_page(wyb, root_element):
    from wybthon import is_hydrating

    seen: list[bool] = []

    @component
    def Inside():
        seen.append(is_hydrating())
        return html(t"<p>client</p>")

    root = wyb["reconciler"].render(html(t"<div>{NoHydration(Inside())}</div>"), root_element)
    assert texts(root_element.element) == ["client"]
    assert seen == [False]
    root.dispose()


def test_is_hydrating_is_true_only_during_the_hydrating_mount(wyb):
    from wybthon import Hydration, is_hydrating

    seen: list[tuple[str, bool]] = []

    @component
    def View():
        seen.append(("body", is_hydrating()))
        on_settled(lambda: seen.append(("settled", is_hydrating())))
        return html(t"""<div>{Hydration(html(t"<p>x</p>"), id="island")}</div>""")

    out = render_to_string(View())
    assert seen == [("body", False)]
    assert "<p>x</p>" in out
    seen.clear()
    result = hydrate_from(wyb, out, View())
    flush()
    assert result.mismatches == 0
    assert seen == [("body", True), ("settled", False)]
    assert not is_hydrating()
