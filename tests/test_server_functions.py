"""Server functions, the wire format, form data, and the response helpers."""

from __future__ import annotations

import asyncio
import datetime
import decimal
import enum
import json
import uuid
from dataclasses import dataclass, field
from typing import Literal, TypedDict

import pytest

from wybthon import (
    FormData,
    RequestEvent,
    ServerError,
    UploadedFile,
    _wire,
    get_request_event,
    redirect,
    reload,
    respond,
    server_function,
    server_functions,
    set_cookie,
)
from wybthon.server_functions import handle
from wybthon.testing import connect_server


class Color(enum.Enum):
    RED = "red"
    BLUE = "blue"


@dataclass
class Point:
    x: int
    y: int = 0


@dataclass
class Shape:
    name: str
    points: list[Point] = field(default_factory=list)
    color: Color = Color.RED


class Options(TypedDict, total=False):
    limit: int
    label: str


# ---------------------------------------------------------------------------
# The wire format
# ---------------------------------------------------------------------------


def test_the_wire_format_round_trips_python_values():
    value = {
        "shape": Shape("tri", [Point(1, 2), Point(3)], Color.BLUE),
        "when": datetime.datetime(2026, 11, 7, 12, 30),
        "day": datetime.date(2026, 11, 7),
        "span": datetime.timedelta(seconds=90),
        "price": decimal.Decimal("9.99"),
        "id": uuid.UUID(int=7),
        "raw": b"\x00\xff",
        "pair": (1, "a"),
        "tags": {"a"},
        "frozen": frozenset({1}),
        "ints": {1: "one"},
        "$dollar": 1,
        "nested": [None, True, 1.5, "s"],
    }
    assert _wire.loads(_wire.dumps(value)) == value


def test_untrusted_decoding_never_builds_classes():
    text = _wire.dumps(Shape("tri", [Point(1)]))
    decoded = _wire.loads(text, trusted=False)
    assert decoded == {"name": "tri", "points": [{"x": 1, "y": 0}], "color": "red"}
    assert _wire.coerce(decoded, Shape) == Shape("tri", [Point(1)])


def test_trusted_decoding_only_resolves_imported_dataclasses():
    text = json.dumps({"$dc": "not.a.module:Thing", "v": {"a": 1}})
    assert _wire.loads(text) == {"a": 1}


def test_values_the_wire_format_cant_send_raise():
    with pytest.raises(_wire.WireError, match="object"):
        _wire.dumps(object())


def test_coerce_validates_against_annotations():
    assert _wire.coerce([1, 2], list[int]) == [1, 2]
    assert _wire.coerce(3, float) == 3.0
    assert _wire.coerce(None, int | None) is None
    assert _wire.coerce("red", Color) is Color.RED
    assert _wire.coerce("a", Literal["a", "b"]) == "a"
    assert _wire.coerce({"limit": 3}, Options) == {"limit": 3}
    assert _wire.coerce("2026-11-07", datetime.date) == datetime.date(2026, 11, 7)
    assert _wire.coerce([1, "x"], tuple[int, str]) == (1, "x")
    assert _wire.coerce({"a": 1}, dict[str, int]) == {"a": 1}
    for value, annotation in [
        (True, int),
        ("1", int),
        ([1, "x"], list[int]),
        ({"x": 1, "z": 2}, Point),
        ({}, Point),
        ({"limit": "3"}, Options),
        ("c", Literal["a", "b"]),
        ("green", Color),
        ("soon", datetime.date),
        (1, FormData),
    ]:
        with pytest.raises(_wire.WireError):
            _wire.coerce(value, annotation)


# ---------------------------------------------------------------------------
# Form data
# ---------------------------------------------------------------------------


def test_form_data_reads_like_a_mapping_with_repeated_fields():
    form = FormData([("tag", "a"), ("tag", "b"), ("title", "Hi")])
    assert form["tag"] == "b" and form.get_all("tag") == ["a", "b"]
    assert "title" in form and form.get("missing", "x") == "x"
    assert form.keys() == ["tag", "title"] and len(form) == 2


def test_form_data_encodes_and_parses_both_encodings():
    form = FormData([("title", "Hi & bye"), ("done", "on")])
    kind, body = form.encode()
    assert kind == "application/x-www-form-urlencoded"
    assert FormData.parse(kind, body) == form
    upload = FormData([("name", "doc"), ("file", UploadedFile("a.txt", "text/plain", b"hello"))])
    kind, body = upload.encode()
    parsed = FormData.parse(kind, body)
    assert parsed["name"] == "doc"
    file = parsed["file"]
    assert isinstance(file, UploadedFile) and file.data == b"hello" and file.filename == "a.txt" and file.size == 5
    with pytest.raises(ValueError):
        FormData.parse("text/plain", b"x")


# ---------------------------------------------------------------------------
# Server functions
# ---------------------------------------------------------------------------


@server_function
async def add_points(a: Point, b: Point) -> Point:
    return Point(a.x + b.x, a.y + b.y)


@server_function(method="GET")
async def count_to(n: int, *, step: int = 1) -> list[int]:
    return list(range(0, n, step))


@server_function
async def fail(message: str) -> None:
    raise ValueError(message)


@server_function
async def fail_on_purpose() -> None:
    raise ServerError("Not allowed", "PermissionError")


@server_function
async def who() -> str:
    event = get_request_event()
    assert event is not None
    set_cookie("seen", "yes", max_age=60)
    return event.headers.get("x-user", "anonymous")


@server_function
async def go_home() -> None:
    raise redirect("/home", revalidate="users")


@server_function
async def touch_nothing() -> int:
    return respond(5, revalidate="")  # type: ignore[return-value]


@server_function
async def refresh_users() -> None:
    return reload(revalidate=["users"])  # type: ignore[return-value]


def test_server_functions_need_a_top_level_async_def():
    with pytest.raises(TypeError, match="async def"):
        server_function(lambda: 1)

    def outer() -> None:
        @server_function
        async def inner() -> None: ...

    with pytest.raises(TypeError, match="top level"):
        outer()
    with pytest.raises(ValueError):
        server_function(method="PUT")


def test_a_server_function_runs_directly_on_the_server():
    assert add_points.id == f"{__name__}:add_points"
    assert add_points.method == "POST" and count_to.method == "GET"
    assert asyncio.run(add_points(Point(1, 2), Point(3, 4))) == Point(4, 6)
    assert asyncio.run(touch_nothing()) == 5


def test_a_call_from_the_browser_crosses_the_wire():
    async def main() -> None:
        assert await add_points(Point(1, 2), Point(3, 4)) == Point(4, 6)
        assert await count_to(6, step=2) == [0, 2, 4]
        with pytest.raises(ServerError) as caught:
            await fail("boom")
        assert caught.value.type_name == "ValueError"
        with pytest.raises(ServerError, match="Not allowed") as caught:
            await fail_on_purpose()
        assert caught.value.type_name == "PermissionError"

    with connect_server():
        asyncio.run(main())


def test_production_hides_unexpected_error_messages():
    from wybthon import set_dev_mode

    set_dev_mode(False)
    try:
        with connect_server(), pytest.raises(ServerError) as caught:
            asyncio.run(fail("secret detail"))
        assert "secret" not in str(caught.value) and caught.value.type_name == "ValueError"
    finally:
        set_dev_mode(True)


def test_mutations_revalidate_and_responses_navigate():
    revalidated: list[object] = []
    navigated: list[str] = []
    previous = server_functions._revalidate_hook, server_functions._navigate_hook
    server_functions._set_hooks(revalidated.append, lambda url, replace: navigated.append(url))

    async def main() -> None:
        await add_points(Point(1), Point(2))
        await count_to(2)
        assert await touch_nothing() == 5
        await refresh_users()
        await go_home()

    try:
        with connect_server():
            asyncio.run(main())
    finally:
        server_functions._set_hooks(*previous)
    # A POST revalidates everything; a GET nothing; `respond(revalidate="")` nothing.
    assert revalidated == [None, [], ["users"], ["users"]]
    assert navigated == ["/home"]


def _call(fn_id: str, payload: object, *, method: str = "POST", headers: dict[str, str] | None = None):
    event = RequestEvent(url="/", method=method, headers=headers or {})
    body = json.dumps(payload).encode()
    query = ""
    if method == "GET":
        from urllib.parse import quote

        query, body = "args=" + quote(json.dumps(payload)), b""
    return asyncio.run(handle(event, fn_id, method, query, {"x-wyb-fn": "1", **(headers or {})}, body))


def test_the_server_validates_untrusted_arguments():
    status, _, body, _, _ = _call(add_points.id, {"args": [{"x": 1}, {"x": "2"}]})
    assert status == 400 and b"b.x" in body
    status, _, _, _, _ = _call(add_points.id, {"args": [{"x": 1}]})
    assert status == 400
    status, _, _, _, _ = _call(count_to.id, {"args": [3], "kwargs": {"nope": 1}}, method="GET")
    assert status == 400
    status, _, _, _, _ = _call(count_to.id, {"args": [3]})
    assert status == 405
    status, _, _, _, _ = _call("tests.nowhere:missing", {"args": []})
    assert status == 404


def test_only_our_own_pages_can_call_without_the_header():
    event = RequestEvent()
    form = b"x=1"
    kind = {"content-type": "application/x-www-form-urlencoded"}
    status, *_ = asyncio.run(handle(event, add_points.id, "POST", "", {"content-type": "application/json"}, b"{}"))
    assert status == 403
    cross = {**kind, "sec-fetch-site": "cross-site"}
    status, *_ = asyncio.run(handle(event, fail.id, "POST", "", cross, form))
    assert status == 403
    other = {**kind, "origin": "https://evil.example", "host": "app.example"}
    status, *_ = asyncio.run(handle(event, fail.id, "POST", "", other, form))
    assert status == 403


def test_a_server_function_reads_the_request_and_sets_cookies():
    event = RequestEvent(headers={"x-user": "ada"})
    status, _, body, _, _ = asyncio.run(handle(event, who.id, "POST", "", {"x-wyb-fn": "1", "x-user": "ada"}, b"{}"))
    assert status == 200 and _wire.loads(body) == {"ok": "ada"}
    assert event.response.headers["set-cookie"][0].startswith("seen=yes")
    assert "HttpOnly" in event.response.headers["set-cookie"][0]


def test_cookies_parse_from_the_request():
    event = RequestEvent(headers={"cookie": 'a=1; b="two words"'})
    assert event.cookies == {"a": "1", "b": "two words"}


def test_redirect_needs_a_redirect_status():
    with pytest.raises(ValueError):
        redirect("/x", 200)
