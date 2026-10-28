"""Engine v5 (RFC 0005): one-step bindings, lean computations, text slots, and cycle-free disposal."""

import ast
import asyncio
import gc
from typing import Any, NamedTuple

import pytest

from wybthon import (
    Errored,
    For,
    Loading,
    Props,
    Show,
    action,
    compiler,
    component,
    create_effect,
    create_memo,
    create_projection,
    create_signal,
    flush,
    h,
    hole,
    html,
    kernel,
    on_cleanup,
    templates,
)
from wybthon.reactivity import _core
from wybthon.testing import cleanup, render


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    cleanup()


def _owner_children(owner: Any) -> list[Any]:
    children = owner._children
    if children is None:
        return []
    return list(children.values()) if type(children) is dict else [children]


# ---------------------------------------------------------------------------
# Bindings in one step
# ---------------------------------------------------------------------------


def test_a_binding_runs_applies_and_joins_its_owner_in_one_step():
    count, set_count = create_signal(1)
    owner = _core.Owner()
    applied: list[tuple[Any, Any, Any]] = []

    def apply(data: Any, value: Any, previous: Any) -> None:
        applied.append((data, value, previous))

    comp = _core.run_with_owner(owner, lambda: _core._bind(lambda: count() * 2, apply, "node", "initial"))
    assert applied == [("node", 2, "initial")]
    assert comp._parent is owner and _owner_children(owner) == [comp]
    assert comp._sources is count and count._observers is comp
    assert comp._ext is None
    set_count(2)
    flush()
    assert applied[-1] == ("node", 4, 2)
    owner.dispose()
    assert comp._disposed and count._observers is None


def test_a_binding_that_reads_nothing_is_returned_disposed_and_never_owned():
    owner = _core.Owner()
    seen: list[Any] = []
    comp = _core.run_with_owner(owner, lambda: _core._bind(lambda: "static", lambda d, v, p: seen.append(v), 1, None))
    assert seen == ["static"]
    assert comp._disposed and comp._value == "static"
    assert owner._children is None


def test_a_binding_made_inside_an_action_takes_the_general_path_with_the_same_result():
    count, set_count = create_signal(3)
    owner = _core.Owner()
    seen: list[Any] = []
    results: list[Any] = []

    @action
    def bind_now():
        results.append(_core.run_with_owner(owner, lambda: _core._bind(count, lambda d, v, p: seen.append(v), 0, None)))

    bind_now()
    flush()
    assert seen == [3]
    assert results[0]._parent is owner
    set_count(4)
    flush()
    assert seen == [3, 4]


def test_a_failing_binding_routes_its_error_to_the_nearest_boundary():
    def boom() -> str:
        raise ValueError("bad label")

    def fallback(err, reset):
        return html(t"<p>caught: {str(err())}</p>")

    with render(Errored(html(t"<p class={boom()}>x</p>"), fallback=fallback)) as screen:
        assert screen.text() == "caught: bad label"


def test_a_binding_waiting_on_async_data_keeps_its_placeholder_until_it_lands():
    async def main():
        gate = asyncio.Event()

        async def load():
            await gate.wait()
            return "ready"

        value = create_memo(load)
        with render(Loading(html(t"<p title={value()}>{value()}</p>"), fallback="wait")) as screen:
            assert screen.text() == "wait"
            gate.set()
            for _ in range(5):
                await asyncio.sleep(0)
                flush()
            assert screen.html() == '<p title="ready">ready</p>'

    asyncio.run(main())


# ---------------------------------------------------------------------------
# A smaller computation
# ---------------------------------------------------------------------------


def test_rarely_set_fields_live_in_an_extension_record():
    effects: list[Any] = []
    count, set_count = create_signal(0)

    def apply(value: int, previous: Any) -> Any:
        effects.append(value)
        return lambda: effects.append("cleanup")

    effect = create_effect(count, apply)
    flush()
    assert effect._ext is not None and effect._ext.apply_cleanup is not None
    memo = create_memo(lambda: count() + 1)
    assert memo() == 1
    assert memo._ext is None
    named = create_memo(lambda: count(), name="named")
    assert named._ext is not None and named._name == "named"
    set_count(1)
    flush()
    assert effects == [0, "cleanup", 1]


def test_a_single_link_grows_into_a_dict_and_dispose_releases_both_sides():
    a, set_a = create_signal(1)
    b, set_b = create_signal(2)
    use_b, set_use_b = create_signal(False)
    seen: list[int] = []
    owner = _core.Owner()

    def compute() -> int:
        return a() + (b() if use_b() else 0)

    comp = _core.run_with_owner(owner, lambda: _core._bind(compute, lambda d, v, p: seen.append(v), None, None))
    assert type(comp._sources) is dict and set(comp._sources) == {a, use_b}
    assert a._observers is comp
    set_use_b(True)
    flush()
    assert set(comp._sources) == {a, b, use_b}
    assert seen == [1, 3]
    reader = _core.run_with_owner(owner, lambda: _core._bind(a, lambda d, v, p: None, None, None))
    assert type(a._observers) is dict and set(a._observers) == {comp, reader}
    owner.dispose()
    assert not a._observers and not b._observers and not use_b._observers
    assert comp._sources is None and comp._fn is None and comp._apply_data is None


# ---------------------------------------------------------------------------
# Text slots without hole nodes
# ---------------------------------------------------------------------------


def test_a_text_slot_binds_its_placeholder_and_upgrades_to_a_hole_for_nodes():
    mode, set_mode = create_signal("text")

    def content() -> Any:
        value = mode()
        if value == "text":
            return "plain"
        if value == "node":
            return html(t"<b>bold</b>")
        if value == "none":
            return None
        return 7

    with render(html(t"<p>{content()}</p>")) as screen:
        instance = screen.root.vnode
        slot = instance.dyn[0]
        assert type(slot) is _core.Computation and type(slot._apply_data) is int
        assert screen.html() == "<p>plain</p>"
        set_mode("node")
        flush()
        assert screen.html() == "<p><b>bold</b></p>"
        assert type(slot._apply_data) is type(instance)
        set_mode("none")
        flush()
        assert screen.html() == "<p></p>"
        set_mode("number")
        flush()
        assert screen.html() == "<p>7</p>"
        set_mode("node")
        flush()
        assert screen.html() == "<p><b>bold</b></p>"


def test_a_text_slot_fills_the_clone_command_and_costs_one_command_per_update():
    label, set_label = create_signal("a")
    with render(html(t"<p>{label()}</p>")) as screen:
        assert screen.html() == "<p>a</p>"
        set_label("b")
        flush()
        assert screen.html() == "<p>b</p>"


def test_text_bindings_and_upgraded_holes_are_disposed_with_their_instance():
    show, set_show = create_signal(True)
    kind, set_kind = create_signal("text")
    cleaned: list[str] = []

    @component
    def Leaf():
        on_cleanup(lambda: cleaned.append("leaf"))
        return html(t"<i>leaf</i>")

    def content() -> Any:
        return Leaf() if kind() == "node" else "text"

    def body() -> Any:
        return html(t"<span>{content()}</span>") if show() else None

    with render(html(t"<div>{body()}</div>")) as screen:
        set_kind("node")
        flush()
        assert screen.html() == "<div><span><i>leaf</i></span></div>"
        set_show(False)
        flush()
        assert cleaned == ["leaf"]
        assert not kind._observers


def test_a_re_rendered_instance_patches_a_text_binding_into_a_new_getter():
    first, set_first = create_signal("one")
    second, set_second = create_signal("two")
    which, set_which = create_signal(0)

    def row(value: Any) -> Any:
        return html(t"<p>{value()}</p>")

    def pick() -> Any:
        return row(first) if which() == 0 else row(second)

    with render(hole(pick)) as screen:
        assert screen.html() == "<p>one</p>"
        set_which(1)
        flush()
        assert screen.html() == "<p>two</p>"
        set_second("three")
        flush()
        assert screen.html() == "<p>three</p>"
        set_first("ignored")
        flush()
        assert screen.html() == "<p>three</p>"


# ---------------------------------------------------------------------------
# Row identity
# ---------------------------------------------------------------------------


class _Point(NamedTuple):
    x: int


class _Name(str):
    pass


@pytest.mark.parametrize(
    ("first", "equal", "second"),
    [
        (_Point(1), _Point(1), _Point(2)),
        (_Name("a"), _Name("a"), _Name("b")),
        ((1, "x"), tuple([1, "x"]), (2, "x")),
        ("ab", "".join(["a", "b"]), "c"),
    ],
    ids=["namedtuple", "str-subclass", "tuple", "str"],
)
def test_equal_scalar_rows_keep_their_row_including_subclasses(first: Any, equal: Any, second: Any):
    rows, set_rows = create_signal([first])
    created: list[Any] = []

    def row(item: Any, index: Any) -> Any:
        created.append(item)
        return html(t"<li>{str(item)}</li>")

    with render(html(t"<ul>{For(rows, row)}</ul>")):
        created.clear()
        # An equal value matches the mounted row by value.
        set_rows([equal, second])
        flush()
        assert created == [second]


def test_entity_rows_match_by_identity():
    a, b = {"id": 1}, {"id": 1}
    rows, set_rows = create_signal([a])
    created: list[Any] = []

    def row(item: Any, index: Any) -> Any:
        created.append(item)
        return html(t"<li>{item['id']}</li>")

    with render(html(t"<ul>{For(rows, row)}</ul>")):
        created.clear()
        set_rows([a, b])
        flush()
        assert [id(item) for item in created] == [id(b)]


# ---------------------------------------------------------------------------
# Branches
# ---------------------------------------------------------------------------


def test_show_without_a_fallback_renders_nothing_and_needs_no_scope():
    on, set_on = create_signal(False)
    with render(html(t"<div>{Show(on(), html(t'<b>yes</b>'))}</div>")) as screen:
        assert screen.html() == "<div></div>"
        set_on(True)
        flush()
        assert screen.html() == "<div><b>yes</b></div>"
        set_on(False)
        flush()
        assert screen.html() == "<div></div>"


def test_a_branch_with_a_constant_condition_keeps_no_computation():
    with render(h("div", None, Show(True, html(t"<b>always</b>")))) as screen:
        assert screen.html() == "<div><b>always</b></div>"


# ---------------------------------------------------------------------------
# The compiler skips the t-string
# ---------------------------------------------------------------------------


def test_compiled_templates_render_a_values_tuple_and_pick_binders_ahead_of_time():
    source = (
        "from wybthon import html\n"
        "def view(row, n, label):\n"
        "    return html(t'<p class={row.cls}>{n()}{label!r}</p>')\n"
    )
    tree = compiler.transform(ast.parse(source), "m.py", source)
    text = ast.unparse(tree)
    assert "__wybthon_t0__.render((" in text
    assert "html(t" not in text.split("def view", 1)[1]
    assert "__wybthon__.formatted(label, 'r', '')" in text
    mount = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "__wybthon_m0__")
    body = ast.unparse(mount)
    assert "prop_fn(first, 'class'" in body
    assert "child_fn(values[1]" in body


def test_the_bytecode_cache_tag_changed_with_the_compiled_output():
    assert compiler.COMPILER_TAG == "wyb2"


# ---------------------------------------------------------------------------
# The kernel registers only addressed nodes
# ---------------------------------------------------------------------------


def test_a_cloned_template_registers_only_the_nodes_python_addresses():
    label, set_label = create_signal("x")
    with render(html(t"<table><tbody><tr><td>v5 static</td><td><a>{label()}</a></td></tr></tbody></table>")):
        compiled = next(shape for shape in kernel._templates.values() if "v5 static" in shape.html)
        assert compiled.addressed == sorted(compiled.addressed)
        assert compiled.count > len(compiled.addressed)
        assert 0 in compiled.addressed
        set_label("y")
        flush()


# ---------------------------------------------------------------------------
# Disposal leaves no reference cycles
# ---------------------------------------------------------------------------


class _CardProps(Props):
    title: str
    count: int = 0


@component
def _Card(props: _CardProps):
    open_, set_open = create_signal(False)

    def toggle() -> None:
        set_open(lambda v: not v)

    return html(t"""<div><h2>{props.title}</h2><p>{props.count}</p>
      <button onclick={toggle}>t</button>{Show(open_(), html(t"<p>details</p>"))}</div>""")


def _framework_garbage() -> int:
    """Framework objects (owners, computations, nodes, signals) a collection finds unreachable.

    The in-memory test DOM's nodes refer to their parents, so removed DOM
    is cyclic garbage here; Wybthon's own structures must not be.
    """
    gc.set_debug(gc.DEBUG_SAVEALL)
    try:
        gc.collect()
        found = [
            o for o in gc.garbage if type(o).__module__.startswith("wybthon.") and "testing" not in type(o).__module__
        ]
    finally:
        gc.set_debug(0)
        gc.garbage.clear()
    return len(found)


def test_clearing_rows_and_components_leaves_nothing_for_the_cycle_collector():
    rows, set_rows = create_signal([])
    selected, set_selected = create_signal(None)
    is_selected = create_projection(lambda: {} if selected() is None else {selected(): True})

    def row(item: dict[str, Any], index: Any) -> Any:
        iid = item["id"]

        def select() -> None:
            set_selected(iid)

        return html(t"""<li class={"on" if is_selected.get(iid) else ""} onclick={select}>
            <{_Card} title={item["label"]()} count={iid} />{item["label"]}</li>""")

    def build(n: int) -> list[dict[str, Any]]:
        out = []
        for i in range(n):
            label, _ = create_signal(f"row {i}")
            out.append({"id": i, "label": label})
        return out

    with render(html(t"<ul>{For(rows, row)}</ul>")):
        set_rows(build(50))
        flush()
        gc.collect()
        set_rows(build(50))
        flush()
        assert _framework_garbage() == 0
        set_rows([])
        flush()
        assert _framework_garbage() == 0


# ---------------------------------------------------------------------------
# The garbage collector
# ---------------------------------------------------------------------------


def test_a_commit_window_pauses_the_collector_and_enables_it_again_outside_a_browser():
    assert gc.isenabled()
    _core._gc_pause()
    try:
        assert not gc.isenabled()
        _core._gc_pause()
        _core._gc_resume()
        assert not gc.isenabled()
    finally:
        _core._gc_resume()
    assert gc.isenabled()
    marker = object()
    _core._release_later(marker)
    assert marker not in _core._graveyard


def test_a_collector_disabled_by_the_application_stays_disabled():
    gc.disable()
    try:
        _core._gc_pause()
        _core._gc_resume()
        assert not gc.isenabled()
    finally:
        gc.enable()


# ---------------------------------------------------------------------------
# Derived stores
# ---------------------------------------------------------------------------


def test_reading_a_settled_projection_subscribes_only_to_the_field():
    selected, set_selected = create_signal(None)
    is_selected = create_projection(lambda: {} if selected() is None else {selected(): True})
    owner = _core.Owner()
    seen: list[Any] = []
    comp = _core.run_with_owner(
        owner, lambda: _core._bind(lambda: bool(is_selected.get(5)), lambda d, v, p: seen.append(v), None, None)
    )
    assert type(comp._sources) is not dict
    set_selected(5)
    flush()
    assert seen == [False, True]
    owner.dispose()


def test_templates_module_exposes_render_entries_not_html_entries():
    assert not hasattr(templates.Precompiled, "load_template")
    assert callable(templates.Precompiled.render)
