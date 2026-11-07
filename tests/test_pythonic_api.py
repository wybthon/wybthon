"""Pythonic forms of Solid's API: `with` blocks, item-only rows, and loud test failures."""

from dataclasses import dataclass, field

import pytest

from wybthon import (
    Errored,
    component,
    create_effect,
    create_root,
    create_signal,
    create_store,
    flush,
    html,
    untrack,
)
from wybthon.testing import fire, render


@dataclass
class Todo:
    title: str
    done: bool = False


@dataclass
class State:
    todos: list[Todo] = field(default_factory=list)


def test_store_edit_blocks_stage_their_changes_together():
    state, set_state = create_store(State([Todo("a")]))
    seen = []
    create_root(lambda dispose: create_effect(lambda: (state.todos[0].title, state.todos[0].done), seen.append))
    flush()
    with set_state.edit() as draft:
        draft.todos[0].title = "b"
        draft.todos[0].done = True
    assert state.todos[0].title == "a"  # staged until the flush
    flush()
    assert seen == [("a", False), ("b", True)]


def test_a_store_edit_block_that_raises_changes_nothing():
    state, set_state = create_store(State([Todo("a")]))
    with pytest.raises(ValueError), set_state.edit() as draft:
        draft.todos[0].title = "b"
        raise ValueError("no")
    flush()
    assert state.todos[0].title == "a"


def test_untrack_as_a_block():
    count, set_count = create_signal(1)
    runs = []

    def compute():
        with untrack():
            value = count()
        runs.append(value)

    create_root(lambda dispose: create_effect(compute, lambda _: None))
    flush()
    set_count(2)
    flush()
    assert runs == [1]


def test_an_error_no_boundary_handles_fails_the_test_that_rendered_it():
    @component
    def Broken():
        def explode():
            raise RuntimeError("boom")

        return html(t"<p>{explode()}</p>")

    with pytest.raises(RuntimeError, match="boom"):
        render(Broken())


def test_an_error_a_boundary_handles_doesnt():
    @component
    def Broken():
        def explode():
            raise RuntimeError("boom")

        return html(t"<p>{explode()}</p>")

    def fallback(err, reset):
        return html(t"<p>caught</p>")

    with render(Errored(Broken(), fallback=fallback)) as screen:
        assert screen.text() == "caught"


def test_an_error_a_click_causes_is_raised_from_fire():
    count, set_count = create_signal(0)

    def check():
        if count() > 0:
            raise RuntimeError("too many")
        return count()

    with render(html(t"<button onclick={(lambda: set_count(1))}>{check()}</button>")) as screen:
        with pytest.raises(RuntimeError, match="too many"):
            fire.click(screen.get_by_role("button"))


def test_a_failed_query_shows_the_markup():
    with render(html(t"<p>hello</p>")) as screen, pytest.raises(LookupError, match="<p>hello</p>"):
        screen.get_by_text("bye")


def test_inputs_are_named_by_their_labels():
    view = html(t"""
      <form>
        <label for="email">Email</label><input id="email" placeholder="you@example.com">
        <label>Name <input></label>
      </form>
    """)
    with render(view) as screen:
        assert screen.get_by_role("textbox", name="Email").attributes["id"] == "email"
        assert screen.get_by_role("textbox", name="Name")


def test_dev_warnings_are_python_warnings():
    from wybthon import For, set_dev_mode
    from wybthon._warnings import _reset_warning_dedupe

    set_dev_mode(True)
    _reset_warning_dedupe()

    def row(item):
        return html(t"<li>{item}</li>")

    # Looked up now: other tests reload Wybthon's modules, which makes a new class.
    from wybthon._warnings import WybthonWarning as current

    with pytest.warns(current, match="plain list"), render(html(t"<ul>{For(['x'], row)}</ul>")):
        pass
