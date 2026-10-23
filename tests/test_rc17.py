"""Solid 2.0 RC.17 alignment (RFC 0004): `create_deferred`, `is_equal`, `is_static`, `flatten`, `on_hydration_end`."""

import asyncio
from collections.abc import Callable
from typing import Any

import pytest
from conftest import StubNode, _StubHTMLParser, collect_texts

from wybthon import (
    Loading,
    Memo,
    ParentProps,
    Props,
    component,
    create_deferred,
    create_effect,
    create_memo,
    create_root,
    create_signal,
    flatten,
    flush,
    html,
    hydrate,
    is_equal,
    is_hydrating,
    is_pending,
    is_server,
    is_static,
    latest,
    merge,
    omit,
    on_hydration_end,
    refresh,
)
from wybthon.dom import Element
from wybthon.reactivity import _core
from wybthon.server import render_to_string


def texts(node: StubNode) -> list[str]:
    return [t for t in collect_texts(node) if t and not t.startswith(("wyb:", "/wyb:"))]


async def _tick(n: int = 5) -> None:
    for _ in range(n):
        flush()
        await asyncio.sleep(0)
    flush()


# ---------------------------------------------------------------------------
# create_deferred
# ---------------------------------------------------------------------------


def _source(make: Callable[..., Any]) -> tuple[Any, Any, Any, dict[int, asyncio.Event]]:
    """An async value keyed by a query signal, built with `make` (`create_memo` or `create_deferred`)."""
    query, set_query = create_signal(1)
    gates = {i: asyncio.Event() for i in range(1, 5)}

    async def fetch() -> str:
        q = query()
        await gates[q].wait()
        return f"rows{q}"

    rows = create_root(lambda dispose: make(fetch))
    return query, set_query, rows, gates


def _view(query: Any, rows: Any) -> Any:
    return html(t"""
      <div>
        <span>{query()}</span>
        {Loading(html(t"<p>{rows()}</p>"), fallback=html(t"<p>wait</p>"))}
        <em>{"refreshing" if is_pending(rows) else "idle"}</em>
      </div>
    """)


def test_deferred_suspends_to_loading_before_its_first_value(wyb, root_element):
    async def main() -> None:
        query, set_query, rows, gates = _source(create_deferred)
        wyb["reconciler"].render(_view(query, rows), root_element)
        flush()
        # A read that isn't ready counts as pending.
        assert texts(root_element.element) == ["1", "wait", "refreshing"]
        assert is_pending(rows)
        gates[1].set()
        await _tick()
        assert texts(root_element.element) == ["1", "rows1", "idle"]

    asyncio.run(main())


@pytest.mark.parametrize("make", [create_memo, create_deferred], ids=["memo", "deferred"])
def test_deferred_refetch_never_holds_the_rest_of_the_ui(wyb, root_element, make):
    async def main() -> None:
        query, set_query, rows, gates = _source(make)
        seen: list[int] = []
        create_root(lambda dispose: create_effect(query, seen.append))
        wyb["reconciler"].render(_view(query, rows), root_element)
        gates[1].set()
        await _tick()
        assert texts(root_element.element) == ["1", "rows1", "idle"]
        set_query(2)
        await _tick()
        if make is create_deferred:
            # Everything else that reads the query moves on; the deferred value lags.
            assert texts(root_element.element) == ["2", "rows1", "refreshing"]
            assert seen == [1, 2]
            assert query() == 2
            assert not _core._transitions
        else:
            # An ordinary async memo holds its input's readers with it.
            assert texts(root_element.element) == ["1", "rows1", "refreshing"]
            assert seen == [1]
        assert is_pending(rows)
        gates[2].set()
        await _tick()
        assert texts(root_element.element) == ["2", "rows2", "idle"]
        assert seen == [1, 2]
        assert not is_pending(rows)
        assert not _core._transitions

    asyncio.run(main())


def test_deferred_keeps_its_last_value_until_the_newest_request_lands(wyb, root_element):
    async def main() -> None:
        query, set_query, rows, gates = _source(create_deferred)
        wyb["reconciler"].render(_view(query, rows), root_element)
        gates[1].set()
        await _tick()
        set_query(2)
        await _tick()
        set_query(3)
        await _tick()
        assert texts(root_element.element) == ["3", "rows1", "refreshing"]
        assert rows() == "rows1"
        gates[2].set()
        await _tick()
        # The superseded request never publishes.
        assert texts(root_element.element) == ["3", "rows1", "refreshing"]
        gates[3].set()
        await _tick()
        assert texts(root_element.element) == ["3", "rows3", "idle"]
        assert latest(rows) == "rows3"

    asyncio.run(main())


def test_deferred_refresh_refetches_quietly(wyb, root_element):
    async def main() -> None:
        server = {"n": 1}
        gate = asyncio.Event()
        gate.set()

        async def load() -> int:
            await gate.wait()
            return server["n"]

        n: Memo[int] = create_root(lambda dispose: create_deferred(load))
        wyb["reconciler"].render(
            html(t"<div>{Loading(html(t'<p>{n() * 10}</p>'), fallback='wait')}<em>{is_pending(n)!s}</em></div>"),
            root_element,
        )
        await _tick()
        assert texts(root_element.element) == ["10", "False"]
        gate.clear()
        server["n"] = 2
        waiting = asyncio.ensure_future(refresh(n))
        await _tick()
        # A refresh is quiet: readers keep the last value and nothing reports pending.
        assert texts(root_element.element) == ["10", "False"]
        assert not waiting.done()
        gate.set()
        assert await waiting == 2
        await _tick()
        assert texts(root_element.element) == ["20", "False"]
        assert not _core._transitions

    asyncio.run(main())


def test_deferred_with_loading_value_never_suspends(wyb, root_element):
    async def main() -> None:
        gate = asyncio.Event()

        async def load() -> list[str]:
            await gate.wait()
            return ["a", "b"]

        tips: Memo[list[str]] = create_root(lambda dispose: create_deferred(load, loading_value=[]))
        wyb["reconciler"].render(html(t"<p>{','.join(tips()) or 'none'}</p>"), root_element)
        flush()
        assert texts(root_element.element) == ["none"]
        gate.set()
        await _tick()
        assert texts(root_element.element) == ["a,b"]

    asyncio.run(main())


def test_deferred_rejects_an_unknown_ssr_source():
    with pytest.raises(ValueError, match="ssr_source"):
        create_deferred(lambda: 1, ssr_source="nowhere")


# ---------------------------------------------------------------------------
# is_equal
# ---------------------------------------------------------------------------


class _NeverEqual:
    def __eq__(self, other: object) -> bool:
        return False

    __hash__ = object.__hash__


class _Raises:
    def __eq__(self, other: object) -> bool:
        raise RuntimeError("no comparison")

    __hash__ = object.__hash__


def test_is_equal_takes_the_identity_fast_path():
    value = _NeverEqual()
    assert is_equal(value, value)
    assert not is_equal(value, _NeverEqual())
    nan = float("nan")
    assert is_equal(nan, nan)
    assert not is_equal(nan, float("nan"))


def test_is_equal_falls_back_to_python_equality():
    assert is_equal(1, 1.0)
    assert is_equal([1, {"a": 2}], [1, {"a": 2}])
    assert is_equal("x", "x")
    assert not is_equal(1, 2)
    assert not is_equal([1], (1,))
    assert not is_equal(None, 0)


def test_is_equal_counts_a_raising_comparison_as_different():
    value = _Raises()
    assert is_equal(value, value)  # identity never calls __eq__
    assert not is_equal(value, _Raises())
    assert not is_equal(_Raises(), 1)


def test_is_equal_is_the_default_signal_policy(wyb):
    value, set_value = create_signal([1, 2])
    runs: list[list[int]] = []
    create_root(lambda dispose: create_effect(value, runs.append))
    flush()
    set_value([1, 2])  # equal: no change
    flush()
    assert runs == [[1, 2]]
    set_value([3])
    flush()
    assert runs == [[1, 2], [3]]


# ---------------------------------------------------------------------------
# is_static
# ---------------------------------------------------------------------------


class ProbeProps(ParentProps):
    label: str = ""
    count: int = 0
    tone: str = "plain"
    on_pick: Callable[[], None] | None = None
    render_row: Callable[[str], Any] | None = None


_KEYS = ("label", "count", "tone", "on_pick", "render_row", "children", "missing")
reports: list[dict[str, bool]] = []


@component
def Probe(props: ProbeProps):
    reports.append({key: is_static(props, key) for key in _KEYS})
    return html(t"<i></i>")


def _report_for(view: Any) -> dict[str, bool]:
    reports.clear()
    from wybthon.testing import cleanup, render

    try:
        render(view)
    finally:
        cleanup()
    assert len(reports) == 1
    return reports[0]


def test_is_static_constant_props_are_static():
    report = _report_for(html(t'<{Probe} label="x" count={3} />'))
    assert report["label"] is True
    assert report["count"] is True


def test_is_static_compiler_getters_and_accessors_are_expressions():
    count, _ = create_signal(1)
    user = {"name": "Ada"}
    report = _report_for(html(t"<{Probe} label={user['name']} count={count} tone={count() and 'loud'} />"))
    assert report["label"] is False  # a compiler getter, even one that reads nothing reactive
    assert report["count"] is False  # an accessor
    assert report["tone"] is False  # a compiler getter that reads a signal


def test_is_static_lambdas_and_python_calls():
    count, _ = create_signal(1)
    report = _report_for(html(t"<{Probe} count={(lambda: count() + 1)} />"))
    assert report["count"] is False
    report = _report_for(Probe(label="x", count=2))
    assert report["label"] is True and report["count"] is True


def test_is_static_callable_fields_and_handlers_are_values():
    def pick() -> None:
        pass

    def row(label: str) -> Any:
        return label

    report = _report_for(html(t"<{Probe} on_pick={pick} render_row={row} />"))
    assert report["on_pick"] is True
    assert report["render_row"] is True
    # A getter for a callable field is still an expression.
    callbacks = {"row": row}
    report = _report_for(html(t"<{Probe} render_row={callbacks['row']} />"))
    assert report["render_row"] is False


def test_is_static_missing_keys_and_children():
    report = _report_for(html(t"<{Probe} />"))
    assert report["missing"] is True
    assert report["label"] is True  # a default the parent didn't pass
    assert report["children"] is True
    report = _report_for(html(t"<{Probe}><b>static</b></{Probe}>"))
    assert report["children"] is True


def test_is_static_on_merge_and_omit_views():
    count, _ = create_signal(1)
    seen: dict[str, bool] = {}

    class ViewProps(Props):
        label: str = ""
        count: int = 0

    @component
    def Viewer(props: ViewProps):
        merged = merge({"label": "default", "extra": 1}, props)
        rest = omit(props, "label")
        seen.update(
            merged_label=is_static(merged, "label"),
            merged_count=is_static(merged, "count"),
            merged_extra=is_static(merged, "extra"),
            merged_missing=is_static(merged, "missing"),
            rest_label=is_static(rest, "label"),
            rest_count=is_static(rest, "count"),
        )
        return html(t"<i></i>")

    from wybthon.testing import cleanup, render

    try:
        render(html(t'<{Viewer} label="x" count={count()} />'))
    finally:
        cleanup()
    assert seen == {
        "merged_label": True,
        "merged_count": False,
        "merged_extra": True,
        "merged_missing": True,
        "rest_label": True,  # omitted: the view doesn't have it
        "rest_count": False,
    }
    accessor_source = merge({"label": count})
    assert is_static(accessor_source, "label") is False
    assert is_static({"label": "x"}, "label") is True


def test_is_static_reads_nothing():
    count, set_count = create_signal(1)
    runs: list[bool] = []

    class OneProps(Props):
        count: int = 0

    @component
    def One(props: OneProps):
        create_effect(lambda: is_static(props, "count"), runs.append)
        return html(t"<i></i>")

    from wybthon.testing import cleanup, render

    try:
        render(html(t"<{One} count={count()} />"))
        assert runs == [False]
        set_count(2)
        flush()
        assert runs == [False]
    finally:
        cleanup()


# ---------------------------------------------------------------------------
# flatten
# ---------------------------------------------------------------------------


def test_flatten_resolves_nested_lists_and_drops_none_and_booleans():
    assert flatten(None) == []
    assert flatten(True) == []
    assert flatten("text") == ["text"]
    assert flatten(0) == [0]
    assert flatten([1, [2, (3, [None, False])], True, "", [[["deep"]]]]) == [1, 2, 3, "", "deep"]


def test_flatten_calls_accessors_and_functions():
    count, _ = create_signal(2)
    items, _ = create_signal(["a", None, ["b"]])
    node = html(t"<b>x</b>")
    assert flatten([count, lambda: [items, lambda: None], node]) == [2, "a", "b", node]


def test_flatten_is_tracked(wyb):
    items, set_items = create_signal([1, [2]])
    flat = create_root(lambda dispose: create_memo(lambda: flatten([0, items])))
    assert flat() == [0, 1, 2]
    set_items([[3, None], True])
    flush()
    assert flat() == [0, 3]


def test_flatten_resolves_component_children():
    seen: list[list[Any]] = []

    @component
    def Count(props: ParentProps):
        seen.append(flatten(props.children))
        return html(t"<i></i>")

    from wybthon.testing import cleanup, render

    name, _ = create_signal("Ada")
    try:
        render(html(t"<{Count}>{name}{None}{[1, [2]]}</{Count}>"))
    finally:
        cleanup()
    assert seen == [["Ada", 1, 2]]


# ---------------------------------------------------------------------------
# on_hydration_end
# ---------------------------------------------------------------------------


def _parse(markup: str) -> StubNode:
    container = StubNode(tag="div")
    parser = _StubHTMLParser(container)
    parser.feed(markup)
    parser.close()
    return container


def _visible(node: Any) -> str:
    if getattr(node, "_is_comment", False):
        return ""
    own = (node.nodeValue or "") if getattr(node, "_is_text", False) else ""
    return own + "".join(_visible(child) for child in node.childNodes)


def _find(node: Any, tag: str) -> Any:
    stack = [node]
    while stack:
        current = stack.pop()
        if current.tag == tag:
            return current
        stack.extend(reversed(current.childNodes))
    raise LookupError(tag)


def test_on_hydration_end_runs_after_hydration_commits(wyb):
    import js

    log: list[Any] = []
    container: list[StubNode] = []

    @component
    def View():
        count, set_count = create_signal(1)

        def bump() -> None:
            set_count(lambda n: n + 1)

        if not is_server():
            create_effect(count, lambda value: log.append(("effect", value)))
            on_hydration_end(lambda: log.append(("end", is_hydrating(), _visible(container[0]))))
            log.append("body")
        return html(t"<div><p>n={count()}</p><button onclick={bump}>+</button></div>")

    markup = render_to_string(View())
    assert log == []
    container.append(_parse(markup))
    backend = wyb["kernel"].PythonBackend(js.document)
    wyb["kernel"].set_backend(backend)
    # A click recorded before hydration replays before the callbacks run.
    backend.queued_events = [("click", _find(container[0], "button"), None)]
    hydrate(View(), Element(node=container[0]))
    # Hydration is over by the time `hydrate` returns: effects ran, input replayed, DOM committed.
    assert log == ["body", ("effect", 1), ("effect", 2), ("end", False, "n=2+")]
    assert backend.hydration_mismatches == 0


def test_on_hydration_end_outside_hydration_runs_on_the_next_tick(wyb, root_element):
    async def main() -> None:
        log: list[str] = []

        @component
        def View():
            on_hydration_end(lambda: log.append(f"end hydrating={is_hydrating()}"))
            log.append("body")
            return html(t"<p>client</p>")

        wyb["reconciler"].render(View(), root_element)
        assert log == ["body"]
        await asyncio.sleep(0)
        assert log == ["body", "end hydrating=False"]
        on_hydration_end(lambda: log.append("late"))
        assert log[-1] != "late"
        await asyncio.sleep(0)
        assert log[-1] == "late"

    asyncio.run(main())
