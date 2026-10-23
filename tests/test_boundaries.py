"""Loading, Reveal, and Errored boundaries."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from conftest import StubNode, collect_texts

from wybthon import html
from wybthon.component import component
from wybthon.error_boundary import Errored
from wybthon.flow import Show
from wybthon.loading import Loading, Reveal
from wybthon.reactivity import create_memo, create_root, create_signal, flush, is_pending, on_cleanup


def texts(node: StubNode) -> list[str]:
    return [t for t in collect_texts(node) if t and t.strip()]


async def _tick(n: int = 3) -> None:
    for _ in range(n):
        flush()
        await asyncio.sleep(0)
    flush()


def _gated_memo(gate: asyncio.Event, value):
    async def load():
        await gate.wait()
        return value

    return create_root(lambda d: create_memo(load))


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def test_loading_shows_fallback_then_content_and_keeps_content_mounted(wyb, root_element):
    async def main() -> None:
        gate = asyncio.Event()
        setups: list[int] = []

        @component
        def UserCard():
            setups.append(1)

            async def load():
                await gate.wait()
                return {"name": "Ada"}

            user = create_memo(load)
            return html(t"<p>User: {user()['name']}</p>")

        view = html(t"<div>{Loading(lambda: UserCard(), fallback=lambda: html(t'<p>Loading...</p>'))}</div>")
        root = wyb["reconciler"].render(view, root_element)
        await _tick()
        assert texts(root_element.element) == ["Loading..."]
        gate.set()
        await _tick()
        assert texts(root_element.element) == ["User: ", "Ada"]
        assert setups == [1]
        root.dispose()
        assert root_element.element.childNodes == []

    asyncio.run(main())


def test_loading_with_ready_content_shows_it_immediately(wyb, root_element):
    view = html(t"<div>{Loading(html(t'<p>ready</p>'), fallback=html(t'<p>wait</p>'))}</div>")
    wyb["reconciler"].render(view, root_element)
    flush()
    assert texts(root_element.element) == ["ready"]


def test_loading_on_waits_for_external_accessors(wyb, root_element):
    async def main() -> None:
        g1, g2 = asyncio.Event(), asyncio.Event()
        a = _gated_memo(g1, 1)
        b = _gated_memo(g2, 2)
        waits = [a, b]
        view = html(t"<div>{Loading(lambda: html(t'<p>static</p>'), fallback=html(t'<p>wait</p>'), on=waits)}</div>")
        wyb["reconciler"].render(view, root_element)
        await _tick()
        assert texts(root_element.element) == ["wait"]
        g1.set()
        await _tick()
        assert texts(root_element.element) == ["wait"]
        g2.set()
        await _tick()
        assert texts(root_element.element) == ["static"]

    asyncio.run(main())


def test_loading_revalidation_keeps_content_and_reports_pending(wyb, root_element):
    async def main() -> None:
        uid, set_uid = create_signal(1)
        gates = {1: asyncio.Event(), 2: asyncio.Event()}

        async def load():
            i = uid()
            await gates[i].wait()
            return f"user{i}"

        @component
        def Card():
            user = create_memo(load)
            return html(t"<p>{user}{' (refreshing)' if is_pending(user) else ''}</p>")

        wyb["reconciler"].render(
            html(t"<div>{Loading(lambda: Card(), fallback=html(t'<p>wait</p>'))}</div>"), root_element
        )
        gates[1].set()
        await _tick()
        assert texts(root_element.element) == ["user1"]
        set_uid(2)
        await _tick()
        # Stale-while-revalidate: content stays, no fallback.
        assert texts(root_element.element) == ["user1", " (refreshing)"]
        gates[2].set()
        await _tick()
        assert texts(root_element.element) == ["user2"]

    asyncio.run(main())


def test_loading_parked_content_keeps_updating_while_hidden(wyb, root_element):
    async def main() -> None:
        gate = asyncio.Event()
        count, set_count = create_signal(0)
        slow = _gated_memo(gate, "ok")
        view = html(t"<div>{Loading(lambda: html(t'<p>{slow}-{count()}</p>'), fallback=html(t'<p>wait</p>'))}</div>")
        wyb["reconciler"].render(view, root_element)
        await _tick()
        assert texts(root_element.element) == ["wait"]
        set_count(5)
        await _tick()
        gate.set()
        await _tick()
        assert texts(root_element.element) == ["ok", "-", "5"]

    asyncio.run(main())


def test_loading_unmount_while_pending_disposes_content(wyb, root_element):
    async def main() -> None:
        gate = asyncio.Event()
        show, set_show = create_signal(True)
        log: list[str] = []

        @component
        def Slow():
            on_cleanup(lambda: log.append("cleanup"))
            m = create_memo(lambda: None)

            async def load():
                await gate.wait()
                return "x"

            data = create_memo(load)
            return html(t"<p>{data}{m}</p>")

        view = html(t"<div>{Show(show, lambda: Loading(lambda: Slow(), fallback=html(t'<p>wait</p>')))}</div>")
        wyb["reconciler"].render(view, root_element)
        await _tick()
        assert texts(root_element.element) == ["wait"]
        set_show(False)
        await _tick()
        assert texts(root_element.element) == []
        assert log == ["cleanup"]
        gate.set()
        await _tick()
        assert texts(root_element.element) == []

    asyncio.run(main())


def test_nested_loading_boundaries_are_independent(wyb, root_element):
    async def main() -> None:
        g_outer, g_inner = asyncio.Event(), asyncio.Event()
        outer = _gated_memo(g_outer, "outer")
        inner = _gated_memo(g_inner, "inner")

        def content() -> Any:
            return html(t"""<div>
                <p>{outer}</p>
                {Loading(lambda: html(t"<p>{inner}</p>"), fallback=html(t"<p>inner-wait</p>"))}
            </div>""")

        wyb["reconciler"].render(
            html(t"<div>{Loading(content, fallback=html(t'<p>outer-wait</p>'))}</div>"), root_element
        )
        await _tick()
        assert texts(root_element.element) == ["outer-wait"]
        g_outer.set()
        await _tick()
        assert texts(root_element.element) == ["outer", "inner-wait"]
        g_inner.set()
        await _tick()
        assert texts(root_element.element) == ["outer", "inner"]

    asyncio.run(main())


def test_loading_children_as_a_component_call_in_a_template(wyb, root_element):
    # `Loading(UserCard(), ...)` in a template: the inner call is prepared
    # by the compiler and mounts under the boundary.
    async def main() -> None:
        gate = asyncio.Event()

        @component
        def UserCard():
            async def load():
                await gate.wait()
                return "Ada"

            name = create_memo(load)
            return html(t"<p>{name}</p>")

        wyb["reconciler"].render(html(t"<div>{Loading(UserCard(), fallback=html(t'<i>wait</i>'))}</div>"), root_element)
        await _tick()
        assert texts(root_element.element) == ["wait"]
        gate.set()
        await _tick()
        assert texts(root_element.element) == ["Ada"]

    asyncio.run(main())


# ---------------------------------------------------------------------------
# Reveal
# ---------------------------------------------------------------------------


def _two_boundaries(ga: asyncio.Event, gb: asyncio.Event):
    ma = _gated_memo(ga, "A")
    mb = _gated_memo(gb, "B")
    return [
        Loading(lambda: html(t"<p>{ma}</p>"), fallback=html(t"<p>fa</p>")),
        Loading(lambda: html(t"<p>{mb}</p>"), fallback=html(t"<p>fb</p>")),
    ]


def test_reveal_sequential_collapsed(wyb, root_element):
    async def main() -> None:
        ga, gb = asyncio.Event(), asyncio.Event()
        boundaries = _two_boundaries(ga, gb)
        wyb["reconciler"].render(html(t"<div>{Reveal(boundaries, collapsed=True)}</div>"), root_element)
        await _tick()
        assert texts(root_element.element) == ["fa"]
        gb.set()
        await _tick()
        assert texts(root_element.element) == ["fa"]
        ga.set()
        await _tick()
        assert texts(root_element.element) == ["A", "B"]

    asyncio.run(main())


def test_reveal_sequential_shows_every_fallback(wyb, root_element):
    async def main() -> None:
        ga, gb = asyncio.Event(), asyncio.Event()
        boundaries = _two_boundaries(ga, gb)
        wyb["reconciler"].render(html(t"<div>{Reveal(boundaries, order='sequential')}</div>"), root_element)
        await _tick()
        assert texts(root_element.element) == ["fa", "fb"]
        gb.set()
        await _tick()
        assert texts(root_element.element) == ["fa", "fb"]  # B waits for A
        ga.set()
        await _tick()
        assert texts(root_element.element) == ["A", "B"]

    asyncio.run(main())


def test_reveal_natural_reveals_independently(wyb, root_element):
    async def main() -> None:
        ga, gb = asyncio.Event(), asyncio.Event()
        boundaries = _two_boundaries(ga, gb)
        wyb["reconciler"].render(html(t"<div>{Reveal(boundaries, order='natural')}</div>"), root_element)
        await _tick()
        assert texts(root_element.element) == ["fa", "fb"]
        gb.set()
        await _tick()
        assert texts(root_element.element) == ["fa", "B"]
        ga.set()
        await _tick()
        assert texts(root_element.element) == ["A", "B"]

    asyncio.run(main())


def test_nested_natural_reveal_is_one_slot_in_parent(wyb, root_element):
    async def main() -> None:
        g_head, g1, g2 = asyncio.Event(), asyncio.Event(), asyncio.Event()
        head = _gated_memo(g_head, "H")
        c1 = _gated_memo(g1, "C1")
        c2 = _gated_memo(g2, "C2")
        view = html(
            t"""<div>{
                Reveal(
                    [
                        Loading(lambda: html(t"<p>{head}</p>"), fallback=html(t"<p>fh</p>")),
                        Reveal(
                            [
                                Loading(lambda: html(t"<p>{c1}</p>"), fallback=html(t"<p>f1</p>")),
                                Loading(lambda: html(t"<p>{c2}</p>"), fallback=html(t"<p>f2</p>")),
                            ],
                            order="natural",
                        ),
                    ]
                )
            }</div>"""
        )
        wyb["reconciler"].render(view, root_element)
        await _tick()
        assert texts(root_element.element) == ["fh", "f1", "f2"]
        g2.set()
        await _tick()
        # The inner group is held on its fallbacks until the header releases it.
        assert texts(root_element.element) == ["fh", "f1", "f2"]
        g_head.set()
        await _tick()
        # Released: each card reveals on its own data.
        assert texts(root_element.element) == ["H", "f1", "C2"]
        g1.set()
        await _tick()
        assert texts(root_element.element) == ["H", "C1", "C2"]

    asyncio.run(main())


def test_reveal_together(wyb, root_element):
    async def main() -> None:
        ga, gb = asyncio.Event(), asyncio.Event()
        boundaries = _two_boundaries(ga, gb)
        wyb["reconciler"].render(html(t"<div>{Reveal(boundaries, order='together')}</div>"), root_element)
        await _tick()
        assert texts(root_element.element) == ["fa", "fb"]
        ga.set()
        await _tick()
        assert texts(root_element.element) == ["fa", "fb"]
        gb.set()
        await _tick()
        assert texts(root_element.element) == ["A", "B"]

    asyncio.run(main())


def test_reveal_validates_arguments(wyb):
    with pytest.raises(ValueError):
        Reveal([], order="sideways")
    with pytest.raises(ValueError):
        Reveal([], collapsed="nope")


# ---------------------------------------------------------------------------
# Errored
# ---------------------------------------------------------------------------


def _risky(boom: bool) -> str:
    if boom:
        raise ValueError("bad")
    return "fine"


def test_errored_shows_fallback_and_resets(wyb, root_element):
    boom, set_boom = create_signal(False)
    resets: list = []
    errors: list[str] = []

    def fallback(err, reset):
        resets.append(reset)
        return html(t"<p>err: {str(err())}</p>")

    wyb["reconciler"].render(
        Errored(
            lambda: html(t"<p>{_risky(boom())}</p>"),
            fallback=fallback,
            on_error=lambda e: errors.append(str(e)),
        ),
        root_element,
    )
    assert texts(root_element.element) == ["fine"]
    set_boom(True)
    flush()
    assert texts(root_element.element) == ["err: ", "bad"]
    assert errors == ["bad"]
    set_boom(False)
    resets[0]()
    flush()
    assert texts(root_element.element) == ["fine"]


def test_errored_fallback_err_is_an_accessor(wyb, root_element):
    from wybthon.reactivity import Accessor

    kind, set_kind = create_signal("")
    seen: list[object] = []

    def risky(k: str) -> str:
        if k:
            raise ValueError(k)
        return "ok"

    def fallback(err, reset):
        seen.append(err)
        return html(t"<p>{type(err()).__name__}: {err()}</p>")

    wyb["reconciler"].render(Errored(lambda: html(t"<p>{risky(kind())}</p>"), fallback=fallback), root_element)
    assert texts(root_element.element) == ["ok"]
    set_kind("first")
    flush()
    assert "".join(texts(root_element.element)) == "ValueError: first"
    assert len(seen) == 1
    err = seen[0]
    assert isinstance(err, Accessor)
    assert callable(err) and not isinstance(err, BaseException)
    assert isinstance(err(), ValueError)
    assert str(err.peek()) == "first"


def test_errored_catches_error_during_initial_render(wyb, root_element):
    def broken():
        raise RuntimeError("init")

    wyb["reconciler"].render(
        Errored(lambda: html(t"<p>{broken}</p>"), fallback=lambda err: html(t"<p>{str(err.peek())}</p>")),
        root_element,
    )
    flush()
    assert texts(root_element.element) == ["init"]


def test_errored_catches_component_body_errors(wyb, root_element):
    @component
    def Broken():
        raise KeyError("missing")

    wyb["reconciler"].render(Errored(lambda: Broken(), fallback="Something failed"), root_element)
    flush()
    assert texts(root_element.element) == ["Something failed"]


def test_errored_default_fallback_text(wyb, root_element):
    def broken():
        raise RuntimeError("x")

    wyb["reconciler"].render(Errored(lambda: html(t"<p>{broken}</p>")), root_element)
    flush()
    assert texts(root_element.element) == ["Something went wrong."]


def test_errored_reset_on_clears_error_when_value_changes(wyb, root_element):
    boom, set_boom = create_signal(True)
    route, set_route = create_signal("/a")
    wyb["reconciler"].render(
        Errored(lambda: html(t"<p>{_risky(boom())}</p>"), fallback=lambda err: html(t"<p>oops</p>"), reset_on=route),
        root_element,
    )
    flush()
    assert texts(root_element.element) == ["oops"]
    set_boom(False)
    set_route("/b")
    flush()
    assert texts(root_element.element) == ["fine"]


def test_errored_tag_reset_on_expression_resets_the_boundary(wyb, root_element):
    # `reset_on={path()}` is dynamic: the boundary reads it through a getter.
    # The failing input here isn't reactive, so only `reset_on` can reset.
    path, set_path = create_signal("/a")
    broken = [True]
    calls: list[int] = []

    def risky() -> str:
        calls.append(1)
        if broken[0]:
            raise ValueError("bad")
        return "fine"

    oops = html(t"<p>oops</p>")
    view = html(t"<main><{Errored} reset_on={path()} fallback={oops}><p>{risky}</p></{Errored}></main>")
    wyb["reconciler"].render(view, root_element)
    flush()
    assert texts(root_element.element) == ["oops"]
    # Setting the same value isn't a change.
    set_path("/a")
    flush()
    assert texts(root_element.element) == ["oops"]
    assert len(calls) == 1
    broken[0] = False
    set_path("/b")
    flush()
    assert texts(root_element.element) == ["fine"]
    assert len(calls) == 2


def test_errored_wrapping_loading_in_a_template(wyb, root_element):
    # `Errored(Loading(Card(), ...))`: arguments are prepared recursively.
    async def main() -> None:
        async def load():
            await asyncio.sleep(0)
            raise ValueError("fetch failed")

        @component
        def Card():
            data = create_memo(load)
            return html(t"<p>{data}</p>")

        view = html(
            t"""<div>{
                Errored(
                    Loading(Card(), fallback=html(t"<p>wait</p>")),
                    fallback=lambda e: html(t"<p>{str(e())}</p>"),
                )
            }</div>"""
        )
        wyb["reconciler"].render(view, root_element)
        await _tick()
        assert texts(root_element.element) == ["fetch failed"]

    asyncio.run(main())


def test_event_handler_errors_are_logged_not_routed_to_errored(wyb, root_element, capsys):
    # Like SolidJS, handlers run outside rendering: the boundary is not
    # involved and the UI stays intact.
    def handler(e):
        raise ValueError("clicked")

    wyb["reconciler"].render(
        Errored(
            lambda: html(t"<button onclick={handler}>go</button>"),
            fallback=lambda err: html(t"<p>{str(err)}</p>"),
        ),
        root_element,
    )
    btn = [n for n in root_element.element.childNodes if n.tag == "button"][0]
    wyb["kernel"]._backend.dispatch("click", btn)
    flush()
    assert texts(root_element.element) == ["go"]
    assert "clicked" in capsys.readouterr().err


def test_nearest_errored_wins(wyb, root_element):
    def broken():
        raise RuntimeError("inner")

    def content() -> Any:
        return html(t"""<div>
            <span>outer-ok</span>
            {Errored(lambda: html(t"<p>{broken}</p>"), fallback=lambda e: html(t"<span>inner-fb</span>"))}
        </div>""")

    wyb["reconciler"].render(Errored(content, fallback=lambda e: html(t"<p>outer-fb</p>")), root_element)
    flush()
    assert texts(root_element.element) == ["outer-ok", "inner-fb"]


def test_errored_catches_async_memo_rejection(wyb, root_element):
    async def main() -> None:
        async def load():
            await asyncio.sleep(0)
            raise ValueError("fetch failed")

        @component
        def Card():
            data = create_memo(load)
            return html(t"<p>{data}</p>")

        wyb["reconciler"].render(
            Errored(
                lambda: Loading(lambda: Card(), fallback=html(t"<p>wait</p>")),
                fallback=lambda e: html(t"<p>{str(e())}</p>"),
            ),
            root_element,
        )
        await _tick()
        assert texts(root_element.element) == ["fetch failed"]

    asyncio.run(main())
