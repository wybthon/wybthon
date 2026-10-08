"""The shipped test renderer (`wybthon.testing`): render, queries, events, and cleanup."""

import asyncio
import os
import re
import subprocess
import sys
import textwrap
from collections.abc import Callable
from pathlib import Path

import pytest

from wybthon import (
    For,
    ParentProps,
    Prop,
    Props,
    Show,
    a,
    button,
    component,
    create_effect,
    create_signal,
    div,
    flush,
    form,
    h1,
    h2,
    input_,
    label,
    li,
    on_cleanup,
    p,
    prop,
    span,
    textarea,
    ul,
)
from wybthon.testing import Screen, TestDocument, TestNode, cleanup, fire, reactive_scope, render, tick, wait_for


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    cleanup()


class CounterProps(Props):
    label: Prop[str]
    initial: Prop[int] = prop(default=0)
    on_change: Callable[[int], None] | None = None


@component
def Counter(props: CounterProps):
    count, set_count = create_signal(props.initial.peek())

    def increment():
        set_count(lambda n: n + 1)
        if props.on_change is not None:
            props.on_change(count.peek() + 1)

    return div(
        p(props.label, ": ", count),
        button("+", on_click=increment, aria_label="increment"),
        button("reset", on_click=lambda: set_count(0)),
    )


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def test_render_returns_a_screen_with_html_and_text():
    screen = render(Counter(label="Clicks", initial=2))
    assert isinstance(screen, Screen)
    assert isinstance(screen.container, TestNode)
    assert screen.text() == "Clicks: 2+reset"  # textContent: no separators between elements
    assert screen.html() == (
        '<div><p>Clicks: 2</p><button aria-label="increment">+</button><button>reset</button></div>'
    )
    assert screen.container.parentNode is not None


def test_counter_example_from_the_rfc():
    changes: list[int] = []
    screen = render(Counter(label="Clicks", on_change=changes.append))
    fire.click(screen.get_by_text("+"))
    assert screen.get_by_text("Clicks: 1")
    fire.click(screen.get_by_role("button", name="increment"))
    assert screen.get_by_text("Clicks: 2")
    assert changes == [1, 2]
    fire.click(screen.get_by_text("reset"))
    assert screen.query_by_text("Clicks: 0") is not None


def test_render_accepts_elements_lists_and_reactive_expressions():
    value, set_value = create_signal("a")
    screen = render([p("one"), p(lambda: f"two {value()}")])
    assert screen.text() == "onetwo a"
    set_value("b")
    flush()
    assert screen.text() == "onetwo b"


def test_html_escapes_text_and_attributes():
    screen = render(div(span("<b>&</b>"), title='say "hi"'))
    assert screen.html() == '<div title="say &quot;hi&quot;"><span>&lt;b&gt;&amp;&lt;/b&gt;</span></div>'


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------


@component
def Page():
    return div(
        h1("Title"),
        h2("Section"),
        ul(li("apple"), li("banana"), li("Apple pie")),
        a("Docs", href="/docs"),
        a("No href"),
        label("Name", html_for="name"),
        input_(id="name"),
        label("Agree", input_(type="checkbox")),
        textarea(aria_label="Notes"),
        input_(placeholder="Search", data_testid="search"),
        span("x", data_testid="item"),
        span("y", data_testid="item"),
        div("custom", role="alert"),
    )


def test_text_queries_get_query_and_get_all():
    screen = render(Page())
    assert screen.get_by_text("apple").tag == "li"
    assert screen.query_by_text("cherry") is None
    assert [n.text_content for n in screen.get_all_by_text("apple", exact=False)] == ["apple", "Apple pie"]
    assert [n.text_content for n in screen.get_all_by_text(re.compile(r"^b"))] == ["banana"]
    # The deepest match wins over ancestors with the same text.
    assert screen.get_by_text("Title").tag == "h1"


def test_text_query_errors():
    screen = render(Page())
    with pytest.raises(LookupError, match="Unable to find"):
        screen.get_by_text("cherry")
    with pytest.raises(LookupError, match="Unable to find"):
        screen.get_all_by_text("cherry")
    with pytest.raises(LookupError, match="Found 2 elements"):
        screen.get_by_text("apple", exact=False)
    with pytest.raises(LookupError, match="Found 2 elements"):
        screen.query_by_text("apple", exact=False)


def test_role_queries():
    screen = render(Page())
    assert [n.text_content for n in screen.get_all_by_role("heading")] == ["Title", "Section"]
    assert screen.get_by_role("heading", name="Section").tag == "h2"
    assert screen.get_by_role("link").attributes["href"] == "/docs"  # an anchor without href has no role
    assert screen.get_by_role("list").tag == "ul"
    assert len(screen.get_all_by_role("listitem")) == 3
    assert screen.get_by_role("checkbox").attributes["type"] == "checkbox"
    assert screen.get_by_role("textbox", name="Notes").tag == "textarea"
    assert screen.get_by_role("textbox", name="Search").attributes["data-testid"] == "search"
    assert screen.get_by_role("alert").text_content == "custom"
    assert screen.get_by_role("listitem", name=re.compile("ban")).text_content == "banana"
    assert screen.query_by_role("dialog") is None
    with pytest.raises(LookupError, match="role 'dialog'"):
        screen.get_by_role("dialog")
    with pytest.raises(LookupError, match="Found 3 elements"):
        screen.get_by_role("listitem")
    with pytest.raises(LookupError):
        screen.get_all_by_role("button", name="missing")


def test_label_queries():
    screen = render(Page())
    assert screen.get_by_label_text("Name").attributes["id"] == "name"
    assert screen.get_by_label_text("Agree").attributes["type"] == "checkbox"
    assert screen.get_by_label_text("Notes").tag == "textarea"
    assert screen.query_by_label_text("Email") is None
    with pytest.raises(LookupError, match="labelled 'Email'"):
        screen.get_by_label_text("Email")


def test_test_id_queries():
    screen = render(Page())
    assert screen.get_by_test_id("search").tag == "input"
    assert [n.text_content for n in screen.get_all_by_test_id("item")] == ["x", "y"]
    assert screen.query_by_test_id("missing") is None
    with pytest.raises(LookupError, match="Found 2 elements"):
        screen.get_by_test_id("item")
    with pytest.raises(LookupError):
        screen.query_by_test_id("item")
    with pytest.raises(LookupError, match=r"\[missing\]"):
        screen.get_all_by_test_id("missing")


def test_queries_see_reactive_updates():
    items, set_items = create_signal(["a"])
    screen = render(ul(For(items, lambda item, index: li(item, data_testid="row"))))
    assert len(screen.get_all_by_test_id("row")) == 1
    set_items(["a", "b", "c"])
    flush()
    assert [n.text_content for n in screen.get_all_by_test_id("row")] == ["a", "b", "c"]
    set_items([])
    flush()
    assert screen.query_by_test_id("row") is None


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------


def test_fire_input_and_change():
    @component
    def Form():
        text, set_text = create_signal("")
        agreed, set_agreed = create_signal(False)
        choice, set_choice = create_signal("")
        return div(
            input_(aria_label="name", on_input=lambda e: set_text(e.target.value)),
            input_(type="checkbox", aria_label="agree", on_change=lambda e: set_agreed(e.target.checked)),
            input_(aria_label="choice", on_change=lambda e: set_choice(e.target.value)),
            p(lambda: f"{text()}|{agreed()}|{choice()}", data_testid="out"),
        )

    screen = render(Form())
    fire.input(screen.get_by_label_text("name"), "Ada")
    assert screen.get_by_test_id("out").text_content == "Ada|False|"
    fire.change(screen.get_by_label_text("agree"), checked=True)
    fire.change(screen.get_by_label_text("choice"), "b")
    assert screen.get_by_test_id("out").text_content == "Ada|True|b"
    assert screen.get_by_label_text("name").value == "Ada"


def test_fire_submit_key_down_focus_blur_and_custom_events():
    log: list[str] = []

    def submitted(event):
        event.prevent_default()
        log.append(f"submit:{event._default_prevented}")

    screen = render(
        form(
            input_(
                aria_label="field",
                on_keydown=lambda e: log.append(f"key:{e.key}:{e.shift_key}"),
                on_focus=lambda: log.append("focus"),
                on_blur=lambda: log.append("blur"),
                on_dblclick=lambda e: log.append(f"dbl:{e.client_x}"),
            ),
            on_submit=submitted,
            aria_label="form",
        )
    )
    field = screen.get_by_label_text("field")
    fire.focus(field)
    fire.key_down(field, "Enter", shift_key=True)
    fire(field, "dblclick", client_x=7)
    fire.blur(field)
    fire.submit(screen.get_by_role("form"))
    assert log == ["focus", "key:Enter:True", "dbl:7", "blur", "submit:True"]


def test_events_bubble_to_ancestor_handlers():
    log: list[str] = []
    screen = render(
        div(button(span("inner"), on_click=lambda: log.append("button")), on_click=lambda e: log.append("div"))
    )
    fire.click(screen.get_by_text("inner"))
    assert log == ["button", "div"]


def test_zero_argument_handlers_and_flushed_updates():
    @component
    def Toggle():
        open_, set_open = create_signal(False)
        return div(
            button("toggle", on_click=lambda: set_open(lambda v: not v)),
            Show(open_, lambda: p("panel")),
        )

    screen = render(Toggle())
    assert screen.query_by_text("panel") is None
    fire.click(screen.get_by_role("button", name="toggle"))
    assert screen.get_by_text("panel").tag == "p"
    fire.click(screen.get_by_role("button", name="toggle"))
    assert screen.query_by_text("panel") is None


def test_fire_with_children_props_component():
    class CardProps(ParentProps):
        title: Prop[str]

    @component
    def Card(props: CardProps):
        return div(h2(props.title), props.children)

    clicks: list[int] = []
    screen = render(Card(title="Hi")[p("body"), button("go", on_click=lambda: clicks.append(1))])
    fire.click(screen.get_by_role("button", name="go"))
    assert clicks == [1]
    assert screen.get_by_role("heading").text_content == "Hi"


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------


def test_context_manager_unmounts_and_runs_cleanups():
    events: list[str] = []

    @component
    def Tracked():
        on_cleanup(lambda: events.append("cleanup"))
        return p("tracked")

    with render(Tracked()) as screen:
        assert screen.text() == "tracked"
        container = screen.container
    assert events == ["cleanup"]
    assert screen.root._disposed
    assert container.childNodes == []
    # Unmounting twice is harmless.
    screen.unmount()
    assert events == ["cleanup"]


def test_cleanup_unmounts_every_screen():
    events: list[str] = []
    value, set_value = create_signal(0)

    @component
    def Watcher():
        create_effect(value, lambda v: events.append(f"effect {v}"))
        on_cleanup(lambda: events.append("cleanup"))
        return p("w")

    first, second = render(Watcher()), render(Watcher())
    assert events == ["effect 0", "effect 0"]
    cleanup()
    assert events == ["effect 0", "effect 0", "cleanup", "cleanup"]
    assert first.root._disposed and second.root._disposed
    set_value(1)
    flush()
    assert "effect 1" not in events
    cleanup()  # nothing left to unmount


def test_renders_share_one_in_memory_document():
    first, second = render(p("a")), render(p("b"))
    document = first.container.parentNode
    assert document is second.container.parentNode
    assert document.tag == "body"
    assert isinstance(TestDocument().body, TestNode)


def test_fire_requires_a_python_backend(monkeypatch):
    from wybthon import kernel

    monkeypatch.setattr(kernel, "_backend", object())
    with pytest.raises(RuntimeError, match="wybthon.testing.render"):
        fire.click(TestNode(tag="button"))


# ---------------------------------------------------------------------------
# Reactive helpers
# ---------------------------------------------------------------------------


def test_reactive_scope_tick_and_wait_for():
    async def main() -> None:
        value, set_value = create_signal(0)
        seen: list[int] = []
        with reactive_scope():
            create_effect(value, seen.append)
            flush()
            set_value(1)
            await tick()
            assert seen == [0, 1]

            async def later() -> None:
                await asyncio.sleep(0.01)
                set_value(5)

            task = asyncio.ensure_future(later())
            await wait_for(lambda: seen[-1] == 5, timeout=1)
            await task
        set_value(6)
        await tick()
        assert seen == [0, 1, 5]
        with pytest.raises(TimeoutError):
            await wait_for(lambda: False, timeout=0.01)
        with pytest.raises(ValueError):
            await tick(0)

    asyncio.run(main())


# ---------------------------------------------------------------------------
# A fresh interpreter, without the test suite's stubs
# ---------------------------------------------------------------------------


def test_works_in_a_fresh_cpython_process():
    script = textwrap.dedent(
        """
        import sys
        assert "js" not in sys.modules and "conftest" not in sys.modules

        from wybthon import Prop, Props, button, component, create_signal, div, p, prop
        from wybthon.testing import cleanup, fire, render


        class CounterProps(Props):
            label: Prop[str]
            initial: Prop[int] = prop(default=0)


        @component
        def Counter(props: CounterProps):
            count, set_count = create_signal(props.initial.peek())
            return div(p(props.label, ": ", count), button("+", on_click=lambda: set_count(lambda n: n + 1)))


        screen = render(Counter(label="Clicks"))
        fire.click(screen.get_by_role("button", name="+"))
        fire.click(screen.get_by_text("+"))
        assert screen.get_by_text("Clicks: 2"), screen.html()
        with render(p("second")) as other:
            assert other.text() == "second"
        cleanup()
        assert screen.root._disposed
        assert "js" not in sys.modules
        print("ok", screen.html() == "")
        """
    )
    src = Path(__file__).resolve().parents[1] / "src"
    env = {**os.environ, "PYTHONPATH": str(src)}
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, env=env, timeout=60, check=False
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok True"
