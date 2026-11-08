"""Regressions found reviewing Engine v8: namespaces on patched slots, effect phases, strict tests, warnings."""

import warnings

import pytest

from wybthon import create_effect, create_root, create_signal, flush, html
from wybthon.testing import cleanup, render
from wybthon.vnode import NS_SVG, hole


def _walk(node):
    yield node
    for child in getattr(node, "childNodes", ()) or ():
        yield from _walk(child)


def test_a_patched_svg_slot_that_turns_into_nodes_keeps_the_namespace():
    shape, set_shape = create_signal(False)

    def group(on):
        # The same literal each time: a re-render patches it slot by slot.
        return html(t"<g>{html(t'<circle r="1"></circle>') if on else 'none'}</g>")

    view = html(t"<svg>{hole(lambda: group(shape()))}</svg>")
    with render(view) as screen:
        set_shape(True)
        flush()
        circles = [n for n in _walk(screen.container) if getattr(n, "tag", None) == "circle"]
        assert len(circles) == 1
        assert circles[0].namespaceURI == NS_SVG


def test_every_effect_computes_before_any_effect_applies():
    count, set_count = create_signal(0)
    order: list[str] = []

    def body(dispose):
        create_effect(lambda: (count(), order.append("compute a"))[0], lambda _v: order.append("apply a"))
        create_effect(lambda: (count(), order.append("compute b"))[0], lambda _v: order.append("apply b"))
        return dispose

    create_root(body)
    flush()
    order.clear()
    set_count(1)
    flush()
    assert order == ["compute a", "compute b", "apply a", "apply b"]


def _broken():
    def explode():
        raise RuntimeError("boom")

    return html(t"<p>{explode()}</p>")


def test_cleanup_with_check_raises_errors_nothing_raised_yet():
    flag, set_flag = create_signal(False)

    def view():
        if flag():
            raise RuntimeError("late")
        return "ok"

    render(html(t"<p>{view()}</p>"))
    set_flag(True)
    flush()  # not a `fire`: nothing has raised the error yet
    with pytest.raises(RuntimeError, match="late"):
        cleanup(check=True)


def test_a_non_strict_view_never_fails_a_strict_one_beside_it():
    with render(html(t"<p>fine</p>")) as screen:
        # The broken view logs its error; the strict view's block still ends cleanly.
        broken = render(_broken(), strict=False)
        broken.unmount()
        assert screen.text() == "fine"


def test_warnings_name_the_line_that_caused_them():
    import wybthon._warnings as module

    module.set_dev_mode(True)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        module.warn("direct")
    assert caught[0].filename == __file__
