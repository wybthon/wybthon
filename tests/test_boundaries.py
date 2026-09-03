"""Loading, Reveal, and Errored boundaries."""

from __future__ import annotations

import asyncio

import pytest
from conftest import StubNode, collect_texts

from wybthon.component import component
from wybthon.error_boundary import Errored
from wybthon.flow import Show
from wybthon.html import button, div, p, span
from wybthon.loading import Loading, Reveal
from wybthon.reactivity import create_memo, create_root, create_signal, flush, is_pending, on_cleanup


def texts(node: StubNode) -> list[str]:
    return [t for t in collect_texts(node) if t]


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
            return p("User: ", lambda: user()["name"])

        root = wyb["reconciler"].render(
            div(Loading(lambda: UserCard(), fallback=lambda: p("Loading..."))), root_element
        )
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
    wyb["reconciler"].render(div(Loading(p("ready"), fallback=p("wait"))), root_element)
    flush()
    assert texts(root_element.element) == ["ready"]


def test_loading_on_waits_for_external_accessors(wyb, root_element):
    async def main() -> None:
        g1, g2 = asyncio.Event(), asyncio.Event()
        a = _gated_memo(g1, 1)
        b = _gated_memo(g2, 2)
        wyb["reconciler"].render(div(Loading(lambda: p("static"), fallback=p("wait"), on=[a, b])), root_element)
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
            return p(user, lambda: " (refreshing)" if is_pending(user) else "")

        wyb["reconciler"].render(div(Loading(lambda: Card(), fallback=p("wait"))), root_element)
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
        wyb["reconciler"].render(
            div(Loading(lambda: p(slow, " ", lambda: str(count())), fallback=p("wait"))), root_element
        )
        await _tick()
        assert texts(root_element.element) == ["wait"]
        set_count(5)
        await _tick()
        gate.set()
        await _tick()
        assert texts(root_element.element) == ["ok", " ", "5"]

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
            return p(data, m)

        wyb["reconciler"].render(div(Show(show, lambda: Loading(lambda: Slow(), fallback=p("wait")))), root_element)
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
        wyb["reconciler"].render(
            div(
                Loading(
                    lambda: div(p(outer), Loading(lambda: p(inner), fallback=p("inner-wait"))),
                    fallback=p("outer-wait"),
                )
            ),
            root_element,
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


# ---------------------------------------------------------------------------
# Reveal
# ---------------------------------------------------------------------------


def _two_boundaries(ga: asyncio.Event, gb: asyncio.Event):
    ma = _gated_memo(ga, "A")
    mb = _gated_memo(gb, "B")
    return [Loading(lambda: p(ma), fallback=p("fa")), Loading(lambda: p(mb), fallback=p("fb"))]


def test_reveal_forwards_collapsed(wyb, root_element):
    async def main() -> None:
        ga, gb = asyncio.Event(), asyncio.Event()
        wyb["reconciler"].render(div(Reveal(_two_boundaries(ga, gb), order="forwards", tail="collapsed")), root_element)
        await _tick()
        assert texts(root_element.element) == ["fa"]
        gb.set()
        await _tick()
        assert texts(root_element.element) == ["fa"]
        ga.set()
        await _tick()
        assert texts(root_element.element) == ["A", "B"]

    asyncio.run(main())


def test_reveal_forwards_visible_shows_every_fallback(wyb, root_element):
    async def main() -> None:
        ga, gb = asyncio.Event(), asyncio.Event()
        wyb["reconciler"].render(div(Reveal(_two_boundaries(ga, gb), order="forwards", tail="visible")), root_element)
        await _tick()
        assert texts(root_element.element) == ["fa", "fb"]
        ga.set()
        await _tick()
        assert texts(root_element.element) == ["A", "fb"]
        gb.set()
        await _tick()
        assert texts(root_element.element) == ["A", "B"]

    asyncio.run(main())


def test_reveal_backwards(wyb, root_element):
    async def main() -> None:
        ga, gb = asyncio.Event(), asyncio.Event()
        wyb["reconciler"].render(div(Reveal(_two_boundaries(ga, gb), order="backwards", tail="hidden")), root_element)
        await _tick()
        assert texts(root_element.element) == []
        ga.set()
        await _tick()
        assert texts(root_element.element) == []  # A waits for B
        gb.set()
        await _tick()
        assert texts(root_element.element) == ["A", "B"]

    asyncio.run(main())


def test_reveal_together(wyb, root_element):
    async def main() -> None:
        ga, gb = asyncio.Event(), asyncio.Event()
        wyb["reconciler"].render(div(Reveal(_two_boundaries(ga, gb), order="together")), root_element)
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
        Reveal([], tail="nope")


# ---------------------------------------------------------------------------
# Errored
# ---------------------------------------------------------------------------


def _risky(boom):
    def render():
        if boom():
            raise ValueError("bad")
        return "fine"

    return render


def test_errored_shows_fallback_and_resets(wyb, root_element):
    boom, set_boom = create_signal(False)
    resets: list = []
    errors: list[str] = []
    wyb["reconciler"].render(
        Errored(
            lambda: p(_risky(boom)),
            fallback=lambda err, reset: (resets.append(reset), p("err: ", str(err)))[1],
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


def test_errored_catches_error_during_initial_render(wyb, root_element):
    def broken():
        raise RuntimeError("init")

    wyb["reconciler"].render(Errored(lambda: p(broken), fallback=lambda err: p(str(err))), root_element)
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

    wyb["reconciler"].render(Errored(lambda: p(broken)), root_element)
    flush()
    assert texts(root_element.element) == ["Something went wrong."]


def test_errored_reset_on_clears_error_when_value_changes(wyb, root_element):
    boom, set_boom = create_signal(True)
    route, set_route = create_signal("/a")
    wyb["reconciler"].render(
        Errored(lambda: p(_risky(boom)), fallback=lambda err: p("oops"), reset_on=route), root_element
    )
    flush()
    assert texts(root_element.element) == ["oops"]
    set_boom(False)
    set_route("/b")
    flush()
    assert texts(root_element.element) == ["fine"]


def test_event_handler_errors_are_logged_not_routed_to_errored(wyb, root_element, capsys):
    # Like SolidJS, handlers run outside rendering: the boundary is not
    # involved and the UI stays intact.
    def handler(e):
        raise ValueError("clicked")

    wyb["reconciler"].render(
        Errored(lambda: button("go", on_click=handler), fallback=lambda err: p(str(err))), root_element
    )
    btn = [n for n in root_element.element.childNodes if n.tag == "button"][0]
    wyb["kernel"]._backend.dispatch("click", btn)
    flush()
    assert texts(root_element.element) == ["go"]
    assert "clicked" in capsys.readouterr().err


def test_nearest_errored_wins(wyb, root_element):
    def broken():
        raise RuntimeError("inner")

    wyb["reconciler"].render(
        Errored(
            lambda: div(span("outer-ok"), Errored(lambda: p(broken), fallback=lambda e: span("inner-fb"))),
            fallback=lambda e: p("outer-fb"),
        ),
        root_element,
    )
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
            return p(data)

        wyb["reconciler"].render(
            Errored(lambda: Loading(lambda: Card(), fallback=p("wait")), fallback=lambda e: p(str(e))),
            root_element,
        )
        await _tick()
        assert texts(root_element.element) == ["fetch failed"]

    asyncio.run(main())
