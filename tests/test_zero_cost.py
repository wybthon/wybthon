"""Zero-cost components (RFC 0003): constant props, inert bindings, native regions, no throwaway placeholders."""

from typing import Any

import pytest

from wybthon import (
    For,
    Match,
    Prop,
    Props,
    Repeat,
    Show,
    Switch,
    component,
    create_signal,
    diagnostics,
    div,
    flush,
    h,
    html,
    kernel,
    on_cleanup,
    p,
    prop,
    span,
)
from wybthon.reactivity import _core
from wybthon.testing import cleanup, render


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    cleanup()


def created_during(fn: Any) -> dict[str, int]:
    """How many signals and computations `fn` constructs."""
    counts = {"Signal": 0, "Computation": 0}
    signal_init, comp_init = _core.Signal.__init__, _core.Computation.__init__

    def count_signal(self, *a, **k):
        counts["Signal"] += 1
        signal_init(self, *a, **k)

    def count_comp(self, *a, **k):
        counts["Computation"] += 1
        comp_init(self, *a, **k)

    setattr(_core.Signal, "__init__", count_signal)
    setattr(_core.Computation, "__init__", count_comp)
    try:
        fn()
    finally:
        setattr(_core.Signal, "__init__", signal_init)
        setattr(_core.Computation, "__init__", comp_init)
    return counts


def ops_during(fn: Any) -> dict[str, int]:
    with diagnostics.profile() as prof:
        fn()
        flush()
        kernel.commit()
    return {k: v for k, v in prof.counts.items() if k.startswith("op_")}


class LabelProps(Props):
    text: Prop[str]
    tone: Prop[str] = prop(default="plain")


@component
def Label(props: LabelProps):
    return html(t"<span class={props.tone}>{props.text}</span>")


# ---------------------------------------------------------------------------
# Constant props and inert bindings
# ---------------------------------------------------------------------------


def test_a_fixed_component_with_constant_props_allocates_no_reactive_nodes():
    # The page root mounts in a patchable context; its component output (and
    # everything in it) doesn't, so the constant props subscribe to nothing.
    @component
    def Page():
        return div(Label(text="a", tone="loud"), Label(text="b"))

    counts = created_during(lambda: render(Page()))
    assert counts == {"Signal": 0, "Computation": 0}


def test_constant_props_still_render():
    @component
    def Page():
        return div(Label(text="a", tone="loud"), Label(text="b"))

    screen = render(Page())
    assert screen.html() == '<div><span class="loud">a</span><span class="plain">b</span></div>'


def test_accessor_props_are_tracked_directly():
    text, set_text = create_signal("a")

    @component
    def Page():
        return div(Label(text=text))

    screen = render(Page())
    set_text("b")
    flush()
    assert screen.text() == "b"


def test_a_patchable_component_receives_new_constants():
    n, set_n = create_signal(1)
    mounts: list[int] = []

    class CountProps(Props):
        value: Prop[int]

    @component
    def Count(props: CountProps):
        mounts.append(1)
        return p(lambda: f"value {props.value()}")

    screen = render(div(lambda: Count(value=n() * 10)))
    set_n(2)
    flush()
    assert screen.text() == "value 20"
    assert mounts == [1]


def test_a_patch_with_unchanged_props_doesnt_notify():
    other, set_other = create_signal(0)
    runs: list[str] = []

    @component
    def Leaf(props: LabelProps):
        def text() -> str:
            runs.append(props.text())
            return props.text()

        return span(text)

    render(div(lambda: (other(), Leaf(text="same"))[1]))
    set_other(1)
    flush()
    assert runs == ["same"]


def live_computations(owner: Any) -> int:
    graph = diagnostics.inspect_graph(owner)
    return sum(1 for node in graph["nodes"] if node["type"] == "Computation" and not node["disposed"])


def test_inert_holes_and_bindings_are_dropped():
    counts = created_during(lambda: render(div(lambda: "static", class_=lambda: "c")))
    assert counts["Computation"] == 2
    screen = render(div(lambda: "static", class_=lambda: "c"))
    assert screen.html() == '<div class="c">static</div>'
    assert live_computations(screen.root._owner) == 0


def test_a_binding_reading_a_signal_stays_live():
    value, set_value = create_signal("a")
    screen = render(div(lambda: value(), class_=lambda: value()))
    set_value("b")
    flush()
    assert screen.html() == '<div class="b">b</div>'


def test_a_binding_with_a_cleanup_stays_alive():
    cleaned: list[int] = []

    def getter() -> str:
        on_cleanup(lambda: cleaned.append(1))
        return "x"

    screen = render(div(getter))
    screen.unmount()
    assert cleaned == [1]


# ---------------------------------------------------------------------------
# Native control flow
# ---------------------------------------------------------------------------


def test_show_is_a_region_not_a_component():
    on, _ = create_signal(True)
    node = Show(on, p("x"))
    assert node.tag == "_branch"


def test_a_re_rendered_show_keeps_its_branch():
    flag, set_flag = create_signal(True)
    other, set_other = create_signal(0)
    mounts: list[int] = []

    @component
    def Body():
        mounts.append(1)
        return p("body")

    screen = render(div(lambda: (other(), Show(flag, lambda: Body()))[1]))
    set_other(1)
    flush()
    assert mounts == [1]
    set_flag(False)
    flush()
    assert screen.text() == ""


def test_a_re_rendered_for_takes_the_new_source():
    first, _ = create_signal(["a", "b"])
    second, _ = create_signal(["c"])
    which, set_which = create_signal(0)
    screen = render(div(lambda: For(first if which() == 0 else second, lambda item, i: span(item))))
    assert screen.text() == "ab"
    set_which(1)
    flush()
    assert screen.text() == "c"


def test_repeat_and_switch_regions():
    n, set_n = create_signal(2)
    mode, set_mode = create_signal("a")
    screen = render(
        div(
            Repeat(n, lambda i: span(str(i))),
            Switch(Match(lambda: mode() == "a", p("A")), fallback=p("other")),
        )
    )
    assert screen.text() == "01A"
    set_n(3)
    set_mode("b")
    flush()
    assert screen.text() == "012other"


# ---------------------------------------------------------------------------
# Placeholders
# ---------------------------------------------------------------------------


def test_a_component_child_followed_by_an_element_needs_no_placeholder():
    @component
    def Page():
        return div(Label(text="a"), span("after"), Label(text="last"))

    counts = ops_during(lambda: render(Page()))
    assert counts.get(f"op_{kernel.OP_DISPOSE}", 0) == 0
    assert counts.get(f"op_{kernel.OP_CREATE_COMMENT}", 0) == 0


def test_adjacent_component_children_keep_one_placeholder():
    @component
    def Page():
        return div(Label(text="a"), Label(text="b"), span("c"))

    screen = render(Page())
    assert screen.text() == "abc"


# ---------------------------------------------------------------------------
# Plain function tags
# ---------------------------------------------------------------------------


def test_a_plain_function_tag_receives_the_props_dict_and_reruns_on_change():
    calls: list[dict[str, Any]] = []

    def Plain(props: dict[str, Any]) -> Any:
        calls.append(props)
        return span(props["label"])

    label, set_label = create_signal("a")
    screen = render(div(lambda: h(Plain, {"label": label()})))
    set_label("b")
    flush()
    assert screen.text() == "b"
    assert [c["label"] for c in calls] == ["a", "b"]
