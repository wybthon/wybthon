"""Zero-cost components: constant props and inert bindings (the static probe), native regions, no placeholders.

Under Engine v4 (RFC 0004), a binding the compiler deferred whose
expression makes no calls (`{props.title}`, `{row["label"]}`) first runs
as a static probe (`wybthon.reactivity._core._probe`). If it reads
nothing reactive, its value is applied and no computation is ever
allocated; if it returns an accessor without reading anything, the
binding re-targets at that accessor.
"""

from typing import Any

import pytest

from wybthon import (
    For,
    Match,
    Props,
    Repeat,
    Show,
    Switch,
    component,
    create_signal,
    diagnostics,
    flush,
    h,
    html,
    kernel,
    on_cleanup,
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


def live_computations(owner: Any) -> int:
    graph = diagnostics.inspect_graph(owner)
    return sum(1 for node in graph["nodes"] if node["type"] == "Computation" and not node["disposed"])


class LabelProps(Props):
    text: str
    tone: str = "plain"


@component
def Label(props: LabelProps):
    return html(t"<span class={props.tone}>{props.text}</span>")


# ---------------------------------------------------------------------------
# Constant props
# ---------------------------------------------------------------------------


def test_a_fixed_component_with_constant_props_allocates_no_reactive_nodes():
    # The page root mounts in a patchable context; its component output (and
    # everything in it) doesn't, so the constant props subscribe to nothing,
    # and each `{props.x}` binding is applied by the probe without a computation.
    @component
    def Page():
        return html(t'<div><{Label} text="a" tone="loud" /><{Label} text="b" /></div>')

    counts = created_during(lambda: render(Page()))
    assert counts == {"Signal": 0, "Computation": 0}


def test_constant_props_still_render():
    @component
    def Page():
        return html(t'<div><{Label} text="a" tone="loud" /><{Label} text="b" /></div>')

    screen = render(Page())
    assert screen.html() == '<div><span class="loud">a</span><span class="plain">b</span></div>'


def test_accessor_props_are_tracked_directly():
    text, set_text = create_signal("a")

    @component
    def Page():
        return html(t"<div><{Label} text={text} /></div>")

    screen = render(Page())
    set_text("b")
    flush()
    assert screen.text() == "b"


def test_getter_props_escape_the_probe_and_stay_live():
    text, set_text = create_signal("a")

    @component
    def Page():
        return html(t"<div><{Label} text={text().upper()} /></div>")

    screen = render(Page())
    assert screen.text() == "A"
    set_text("b")
    flush()
    assert screen.text() == "B"


def test_a_patchable_component_receives_new_constants():
    n, set_n = create_signal(1)
    mounts: list[int] = []

    class CountProps(Props):
        value: int

    @component
    def Count(props: CountProps):
        mounts.append(1)
        return html(t"<p>value {props.value}</p>")

    # The hole returns a new node with a constant prop each time; the
    # mounted component is patched, not remounted.
    screen = render(html(t"<div>{(lambda: Count(value=n() * 10))}</div>"))
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
            runs.append(props.text)
            return props.text

        return html(t"<span>{text}</span>")

    render(html(t"<div>{(lambda: (other(), Leaf(text='same'))[1])}</div>"))
    set_other(1)
    flush()
    assert runs == ["same"]


# ---------------------------------------------------------------------------
# Inert bindings and the static probe
# ---------------------------------------------------------------------------


def test_inert_compiled_bindings_allocate_no_computation():
    class Item:
        name = "static"

    row = {"cls": "c"}
    item = Item()
    counts = created_during(lambda: render(html(t"<div class={row['cls']}>{item.name}</div>")))
    assert counts == {"Signal": 0, "Computation": 0}
    screen = render(html(t"<div class={row['cls']}>{item.name}</div>"))
    assert screen.html() == '<div class="c">static</div>'
    assert live_computations(screen.root._owner) == 0


def test_expressions_with_calls_are_not_probed_but_inert_ones_are_dropped():
    # A call might read a signal, so the binding runs as a computation; one
    # that read nothing reactive is disposed after its first run.
    def label() -> str:
        return "static"

    counts = created_during(lambda: render(html(t"<div class={label()}>{label()}</div>")))
    assert counts["Computation"] == 2
    screen = render(html(t"<div class={label()}>{label()}</div>"))
    assert screen.html() == '<div class="static">static</div>'
    assert live_computations(screen.root._owner) == 0


def test_inert_lambdas_are_dropped_after_one_run():
    counts = created_during(lambda: render(html(t"<div class={(lambda: 'c')}>{(lambda: 'static')}</div>")))
    assert counts["Computation"] == 2
    screen = render(html(t"<div class={(lambda: 'c')}>{(lambda: 'static')}</div>"))
    assert screen.html() == '<div class="c">static</div>'
    assert live_computations(screen.root._owner) == 0


def test_a_probe_that_returns_a_signal_binds_to_it():
    label, set_label = create_signal("a")
    tone, set_tone = create_signal("x")
    row = {"label": label, "tone": tone}
    counts = created_during(lambda: render(html(t"<p class={row['tone']}>{row['label']}</p>")))
    # One computation per binding, created directly on the signal.
    assert counts == {"Signal": 0, "Computation": 2}
    cleanup()
    screen = render(html(t"<p class={row['tone']}>{row['label']}</p>"))
    set_label("b")
    set_tone("y")
    flush()
    assert screen.html() == '<p class="y">b</p>'


def test_a_binding_reading_a_signal_stays_live():
    value, set_value = create_signal("a")
    screen = render(html(t"<div class={value()}>{value()}</div>"))
    set_value("b")
    flush()
    assert screen.html() == '<div class="b">b</div>'


def test_a_prop_read_that_reaches_a_signal_escapes_the_probe():
    value, set_value = create_signal("a")

    class Box:
        @property
        def label(self) -> str:
            return value()

    box = Box()
    counts = created_during(lambda: render(html(t"<p>{box.label}</p>")))
    assert counts["Computation"] == 1
    cleanup()
    screen = render(html(t"<p>{box.label}</p>"))
    set_value("b")
    flush()
    assert screen.text() == "b"


def test_a_binding_with_a_cleanup_stays_alive():
    cleaned: list[int] = []

    def getter() -> str:
        on_cleanup(lambda: cleaned.append(1))
        return "x"

    screen = render(html(t"<div>{getter}</div>"))
    screen.unmount()
    assert cleaned == [1]


def test_a_probed_expression_that_registers_a_cleanup_gets_a_computation():
    # Ownership (a cleanup, a child scope) ends the probe, so the binding
    # runs as a computation that owns the cleanup.
    cleaned: list[int] = []

    class Resource:
        @property
        def label(self) -> str:
            on_cleanup(lambda: cleaned.append(1))
            return "x"

    resource = Resource()
    screen = render(html(t"<div>{resource.label}</div>"))
    assert screen.text() == "x"
    screen.unmount()
    assert cleaned == [1]


# ---------------------------------------------------------------------------
# Native control flow
# ---------------------------------------------------------------------------


def test_show_is_a_region_not_a_component():
    on, _ = create_signal(True)
    node = Show(on, html(t"<p>x</p>"))
    assert node.tag == "_branch"


def test_a_re_rendered_show_keeps_its_branch():
    flag, set_flag = create_signal(True)
    other, set_other = create_signal(0)
    mounts: list[int] = []

    @component
    def Body():
        mounts.append(1)
        return html(t"<p>body</p>")

    screen = render(html(t"<div>{(lambda: (other(), Show(flag, lambda: Body()))[1])}</div>"))
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

    def row(item: Any, i: Any) -> Any:
        return html(t"<span>{item}</span>")

    screen = render(html(t"<div>{(lambda: For(first if which() == 0 else second, row))}</div>"))
    assert screen.text() == "ab"
    set_which(1)
    flush()
    assert screen.text() == "c"


def test_repeat_and_switch_regions():
    n, set_n = create_signal(2)
    mode, set_mode = create_signal("a")

    def item(i: int) -> Any:
        return html(t"<span>{i}</span>")

    shown = html(t"<p>A</p>")
    other = html(t"<p>other</p>")
    screen = render(html(t"<div>{Repeat(n, item)}{Switch(Match(mode() == 'a', shown), fallback=other)}</div>"))
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
        return html(t'<div><{Label} text="a" /><span>after</span><{Label} text="last" /></div>')

    counts = ops_during(lambda: render(Page()))
    assert counts.get(f"op_{kernel.OP_DISPOSE}", 0) == 0
    assert counts.get(f"op_{kernel.OP_CREATE_COMMENT}", 0) == 0


def test_adjacent_component_children_keep_one_placeholder():
    @component
    def Page():
        return html(t'<div><{Label} text="a" /><{Label} text="b" /><span>c</span></div>')

    screen = render(Page())
    assert screen.text() == "abc"


# ---------------------------------------------------------------------------
# Plain function tags
# ---------------------------------------------------------------------------


def test_a_plain_function_tag_receives_the_props_dict_and_reruns_on_change():
    calls: list[dict[str, Any]] = []

    def Plain(props: dict[str, Any]) -> Any:
        calls.append(props)
        return html(t"<span>{props['label']}</span>")

    label, set_label = create_signal("a")
    screen = render(html(t"<div>{(lambda: h(Plain, {'label': label()}))}</div>"))
    set_label("b")
    flush()
    assert screen.text() == "b"
    assert [c["label"] for c in calls] == ["a", "b"]


def test_a_patched_show_keeps_its_branch_and_reads_the_new_value():
    value, set_value = create_signal(1)
    mounts: list[int] = []

    def branch(current: Any) -> Any:
        mounts.append(1)
        return html(t"<span>{current}</span>")

    screen = render(html(t"<div>{(lambda: Show(value(), branch))}</div>"))
    set_value(2)
    flush()
    assert screen.text() == "2"
    assert mounts == [1]
    set_value(0)
    flush()
    assert screen.text() == ""


def test_a_patched_switch_match_reads_the_new_condition_value():
    value, set_value = create_signal("a")

    def branch(current: Any) -> Any:
        return html(t"<span>{current}</span>")

    none = html(t"<p>none</p>")
    screen = render(html(t"<div>{(lambda: Switch(Match(value(), branch), fallback=none))}</div>"))
    set_value("b")
    flush()
    assert screen.text() == "b"
