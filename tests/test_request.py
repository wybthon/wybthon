"""The request event and response head declared during server renders (`wybthon.request`)."""

import asyncio

from wybthon import (
    Errored,
    Loading,
    Props,
    RequestEvent,
    ResponseHead,
    Show,
    component,
    create_memo,
    create_signal,
    flush,
    get_request_event,
    html,
    http_header,
    http_status,
    untrack,
)
from wybthon.server import render_to_stream, render_to_string


class StatusProps(Props):
    code: int


@component
def Status(props: StatusProps):
    http_status(untrack(lambda: props.code))
    return html(t"<p>status</p>")


def test_defaults():
    event = RequestEvent()
    assert event.url == "/"
    assert event.request is None
    assert event.locals == {}
    assert event.response == ResponseHead(status=200, status_text=None, headers={}, committed=False)
    # Each event gets its own mutable containers.
    assert RequestEvent().locals is not event.locals
    assert RequestEvent().response.headers is not event.response.headers


def test_get_request_event_during_a_server_render():
    seen: list[RequestEvent | None] = []
    request = object()
    event = RequestEvent(url="/start", request=request, locals={"user": "ada"})

    @component
    def View():
        current = get_request_event()
        seen.append(current)
        assert current is not None
        return html(t"<p>user {current.locals['user']}</p>")

    out = render_to_string(View(), url="/users/1", event=event)
    assert "user ada" in out
    assert seen == [event]
    # An explicit url overrides the event's.
    assert event.url == "/users/1"
    assert event.request is request
    assert get_request_event() is None


def test_render_without_an_event_creates_one():
    seen: list[RequestEvent | None] = []

    @component
    def View():
        seen.append(get_request_event())
        return html(t"<p>x</p>")

    render_to_string(View(), url="/about")
    assert seen[0] is not None and seen[0].url == "/about"
    render_to_string(View())
    assert seen[1] is not None and seen[1].url == "/"


def test_status_and_headers_are_declared_on_the_response():
    event = RequestEvent()

    @component
    def View():
        http_status(404, "Not Found")
        http_header("Content-Language", "en")
        http_header("X-Frame-Options", "DENY")
        http_header("x-frame-options", "SAMEORIGIN")  # replaces, case-insensitively
        return html(t"<p>missing</p>")

    render_to_string(View(), event=event)
    head = event.response
    assert head.status == 404
    assert head.status_text == "Not Found"
    assert head.headers == {"content-language": ["en"], "x-frame-options": ["SAMEORIGIN"]}
    assert head.committed is True


def test_header_append_keeps_every_value_in_order():
    event = RequestEvent()

    @component
    def View():
        http_header("Set-Cookie", "a=1")
        http_header("set-cookie", "b=2", append=True)
        http_header("set-cookie", "c=3", append=True)
        http_header("x-new", "first", append=True)  # appending to nothing sets
        return html(t"<p>x</p>")

    render_to_string(View(), event=event)
    assert event.response.headers == {"set-cookie": ["a=1", "b=2", "c=3"], "x-new": ["first"]}
    assert event.response.header_items() == [
        ("set-cookie", "a=1"),
        ("set-cookie", "b=2"),
        ("set-cookie", "c=3"),
        ("x-new", "first"),
    ]


def test_the_deepest_live_declaration_wins():
    event = RequestEvent()

    @component
    def View():
        http_status(201)
        return html(t"<div>{Status(code=202)}{Status(code=203)}</div>")

    render_to_string(View(), event=event)
    assert event.response.status == 203


def test_declarations_are_retracted_when_an_errored_boundary_recovers():
    event = RequestEvent()

    @component
    def Broken():
        http_status(404)
        http_header("x-broken", "1")
        http_header("x-kept", "inner", append=True)
        raise ValueError("boom")

    @component
    def View():
        http_status(201)
        http_header("x-kept", "outer")
        return html(t"<div>{Errored(Broken(), fallback=lambda err, reset: html(t'<p>{f"error: {err()}"}</p>'))}</div>")

    out = render_to_string(View(), event=event)
    assert "error: boom" in out
    head = event.response
    assert head.status == 201
    assert head.headers == {"x-kept": ["outer"]}


def test_a_fallback_can_declare_its_own_status():
    event = RequestEvent()

    @component
    def Broken():
        http_status(404)
        raise ValueError("boom")

    def fallback(err, reset):
        http_status(500, "Internal Server Error")
        return html(t"<p>sorry</p>")

    render_to_string(Errored(lambda: Broken(), fallback=fallback), event=event)
    assert (event.response.status, event.response.status_text) == (500, "Internal Server Error")


def test_a_fallback_status_sticks_when_the_failed_child_declared_nothing():
    event = RequestEvent()

    @component
    def Broken():
        raise ValueError("boom")

    def fallback(err, reset):
        http_status(500)
        http_header("x-error", type(err()).__name__)
        return html(t"<p>sorry</p>")

    render_to_string(Errored(lambda: Broken(), fallback=fallback), event=event)
    assert event.response.status == 500
    assert event.response.headers == {"x-error": ["ValueError"]}


def test_fallback_declarations_are_retracted_when_content_replaces_them():
    event = RequestEvent()

    async def load() -> str:
        await asyncio.sleep(0)
        return "ready"

    @component
    def Pending():
        http_status(503)
        http_header("retry-after", "1")
        return html(t"<p>wait</p>")

    @component
    def Data():
        value = create_memo(load)
        return html(t"<p>{value}</p>")

    async def main() -> str:
        # The first pass shows the fallback; its scope is disposed before
        # the final pass renders the content and commits the head.
        return await render_to_stream(Loading(lambda: Data(), fallback=Pending()), event=event)

    out = asyncio.run(main())
    assert "ready" in out and "wait" not in out
    assert event.response.status == 200
    assert event.response.headers == {}


def test_show_branch_declarations_follow_the_rendered_branch():
    def render(missing: bool) -> RequestEvent:
        event = RequestEvent()
        flag, _set_flag = create_signal(missing)
        render_to_string(
            html(t"<main>{Show(flag(), lambda: Status(code=404), fallback=html(t'<p>found</p>'))}</main>"), event=event
        )
        return event

    assert render(True).response.status == 404
    assert render(False).response.status == 200


def test_committed_head_ignores_later_writes():
    event = RequestEvent()
    render_to_string(Status(code=404), event=event)
    assert event.response.committed
    # A second render with the committed event can't change the head,
    # and disposing the first render after the commit didn't retract it.
    render_to_string(html(t"<div>{Status(code=500)}</div>"), event=event)
    assert event.response.status == 404


def test_awaited_stream_commits_the_final_passes_head():
    event = RequestEvent()

    async def load() -> str:
        await asyncio.sleep(0)
        return "data"

    @component
    def Data():
        value = create_memo(load)

        def body():
            text = value()
            http_header("x-data", text)
            return html(t"<p>{text}</p>")

        return html(t"<div>{body}</div>")

    @component
    def View():
        http_status(201)
        return Loading(lambda: Data(), fallback="wait")

    async def main() -> str:
        return await render_to_stream(View(), event=event)

    out = asyncio.run(main())
    assert "data" in out
    assert event.response.status == 201
    assert event.response.headers == {"x-data": ["data"]}
    assert event.response.committed


def _streaming_app(gate_holder: dict[str, asyncio.Event]):
    async def load() -> str:
        await gate_holder["gate"].wait()
        return "late"

    @component
    def Data():
        value = create_memo(load)

        def body():
            text = value()  # not ready in the shell
            http_status(418)
            http_header("x-late", text)
            return html(t"<p>{text}</p>")

        return html(t"<div>{body}</div>")

    @component
    def View():
        http_status(201)
        http_header("x-shell", "yes")
        return html(t"<div>{Loading(Data(), fallback='wait')}</div>")

    return View


def test_stream_ignores_declarations_after_the_first_chunk():
    event = RequestEvent()

    async def main() -> list[tuple[bool, int]]:
        holder = {"gate": asyncio.Event()}
        View = _streaming_app(holder)
        seen = []
        async for chunk in render_to_stream(View(), event=event):
            seen.append((event.response.committed, event.response.status))
            holder["gate"].set()
            assert chunk
        return seen

    seen = asyncio.run(main())
    assert len(seen) >= 2
    assert all(committed for committed, _status in seen)
    assert event.response.status != 418
    assert "x-late" not in event.response.headers


def test_stream_commits_the_shells_head_with_the_first_chunk():
    event = RequestEvent()

    async def main() -> None:
        holder = {"gate": asyncio.Event()}
        View = _streaming_app(holder)
        async for _chunk in render_to_stream(View(), event=event):
            assert event.response.committed
            assert event.response.status == 201
            assert event.response.headers == {"x-shell": ["yes"]}
            holder["gate"].set()

    asyncio.run(main())


# ---------------------------------------------------------------------------
# In the browser
# ---------------------------------------------------------------------------


def test_request_helpers_are_no_ops_in_the_browser(wyb, root_element):
    seen: list[RequestEvent | None] = []

    @component
    def View():
        seen.append(get_request_event())
        http_status(404)
        http_header("x-anything", "1", append=True)
        return html(t"<p>client</p>")

    root = wyb["reconciler"].render(View(), root_element)
    assert seen == [None]
    root.dispose()


def test_request_helpers_are_no_ops_outside_any_render():
    assert get_request_event() is None
    http_status(500)
    http_header("x", "y")
    assert get_request_event() is None


def test_request_helpers_are_no_ops_while_hydrating(wyb):
    from conftest import StubNode, _StubHTMLParser

    from wybthon import hydrate
    from wybthon.dom import Element

    @component
    def View():
        http_status(404)
        return html(t"<p>x {str(get_request_event())}</p>")

    event = RequestEvent()
    out = render_to_string(View(), event=event)
    assert event.response.status == 404
    assert "x None" not in out
    container = StubNode(tag="div")
    parser = _StubHTMLParser(container)
    parser.feed(out)
    parser.close()
    root = hydrate(View(), Element(node=container))
    flush()
    assert event.response.status == 404
    root.dispose()
