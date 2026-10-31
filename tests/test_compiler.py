"""The template compiler (RFC 0004): wrapping rules, captures, dispatch, precompiled entries, and where it runs."""

from __future__ import annotations

import ast
import importlib
import importlib.util
import marshal
import sys
import textwrap
from pathlib import Path
from typing import Any

import pytest

from wybthon import _hook, compiler, templates
from wybthon.reactivity._core import _Getter


def _tree(source: str) -> ast.Module:
    source = textwrap.dedent(source)
    tree = compiler.transform(ast.parse(source), "m.py", source)
    tree.original = ast.parse(source)  # type: ignore[attr-defined]
    return tree


def _interpolations(tree: ast.AST) -> dict[str, ast.expr]:
    """Each interpolation's source text mapped to the value the compiler passes in its place.

    A compiled `html(t"...")` call becomes `__wybthon_tN__.render((value, ...))`
    at the same position, with one value per interpolation, in order.
    """
    texts: dict[tuple[int, int], list[str]] = {}
    for node in ast.walk(tree.original):  # type: ignore[attr-defined]
        if isinstance(node, ast.Call) and node.args and isinstance(node.args[0], ast.TemplateStr):
            items = [value.str for value in node.args[0].values if isinstance(value, ast.Interpolation)]
            texts[(node.lineno, node.col_offset)] = items
    found: dict[str, ast.expr] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "render":
            values = node.args[0]
            assert isinstance(values, ast.Tuple)
            found.update(zip(texts[(node.lineno, node.col_offset)], values.elts, strict=True))
    return found


def _run(source: str) -> dict[str, Any]:
    namespace: dict[str, Any] = {"__name__": "compiled_test_module"}
    exec(compiler.compile_source(textwrap.dedent(source), "m.py"), namespace)
    return namespace


def _kind(expr: ast.expr) -> str:
    """Describe what the compiler made of an interpolation: verbatim, lambda, getter, or call."""
    if isinstance(expr, ast.Lambda):
        return "lambda"
    if isinstance(expr, ast.Call) and isinstance(expr.func, ast.Attribute) and isinstance(expr.func.value, ast.Name):
        if expr.func.value.id == "__wybthon__":
            return expr.func.attr
    return "verbatim"


HEADER = """
from wybthon import For, Props, Show, component, create_signal, flush, html
"""


# ---------------------------------------------------------------------------
# Which expressions are deferred
# ---------------------------------------------------------------------------


def test_dynamic_child_and_attribute_expressions_become_lambdas():
    found = _interpolations(
        _tree(
            HEADER
            + """
def view(count, row, active, kind, label):
    return html(t'<p class={"on" if active() else ""} title="{kind()} card">{count() * 2}{row["x"]}{label}</p>')
"""
        )
    )
    assert _kind(found["count() * 2"]) == "lambda"
    assert _kind(found['row["x"]']) == "lambda"
    assert _kind(found['"on" if active() else ""']) == "lambda"
    assert _kind(found["kind()"]) == "lambda"
    assert _kind(found["label"]) == "verbatim"


def test_handlers_refs_spreads_and_tags_are_verbatim():
    found = _interpolations(
        _tree(
            HEADER
            + """
def view(make, ref_for, attrs, Card):
    return html(t'<div><button onclick={make(1)} ref={ref_for("b")} {attrs.copy()}>x</button><{Card} /></div>')
"""
        )
    )
    assert _kind(found["make(1)"]) == "verbatim"
    assert _kind(found['ref_for("b")']) == "verbatim"
    assert _kind(found["attrs.copy()"]) == "verbatim"
    assert _kind(found["Card"]) == "verbatim"


def test_component_tag_attributes_become_getters_and_handler_names_stay_verbatim():
    found = _interpolations(
        _tree(
            HEADER
            + """
def view(Card, user, close_for):
    return html(t'<{Card} title={user().name} on_close={close_for(1)} />')
"""
        )
    )
    assert _kind(found["user().name"]) == "getter"
    assert _kind(found["close_for(1)"]) == "verbatim"


def test_calls_in_child_position_are_dispatched_and_nested_markup_is_left_alone():
    found = _interpolations(
        _tree(
            HEADER
            + """
def view(flag, n):
    return html(t'<div>{Show(flag(), html(t"<b>{n()}</b>"))}{html(t"<i>x</i>")}</div>')
"""
        )
    )
    assert _kind(found['Show(flag(), html(t"<b>{n()}</b>"))']) == "call"
    assert _kind(found['html(t"<i>x</i>")']) == "verbatim"
    assert _kind(found["n()"]) == "lambda"


def test_lambdas_names_and_constants_are_verbatim():
    found = _interpolations(
        _tree(
            HEADER
            + """
def view(count):
    return html(t'<p>{count}{(lambda: count() + 1)}{3}{"text"}</p>')
"""
        )
    )
    assert all(_kind(found[key]) == "verbatim" for key in ("count", "3", '"text"'))
    # The author's own lambda is passed as written, not wrapped again.
    assert ast.unparse(found["(lambda: count() + 1)"]) == "lambda: count() + 1"


def test_assignment_expressions_stay_eager():
    found = _interpolations(
        _tree(
            HEADER
            + """
def view(f):
    return html(t'<p>{(y := f())}</p>')
"""
        )
    )
    assert _kind(found["(y := f())"]) == "verbatim"


def test_format_specs_and_conversions_fold_into_the_lambda():
    found = _interpolations(
        _tree(
            HEADER
            + """
def view(price, name):
    return html(t'<p>{price():.2f} {name()!r}</p>')
"""
        )
    )
    price = found["price()"]
    assert isinstance(price, ast.Lambda)
    assert "__wybthon__.fmt" in ast.unparse(price)
    # The value passed for the slot is the lambda itself: nothing is left to format at run time.
    assert "__wybthon__.formatted" not in ast.unparse(price)


def test_static_values_with_format_specs_are_formatted_when_the_template_is_created():
    found = _interpolations(_tree(HEADER + "def v(p, n):\n    return html(t'<p>{p:.2f} {n!r}</p>')\n"))
    assert _kind(found["p"]) == "formatted"
    assert _kind(found["n"]) == "formatted"
    ns = _run(HEADER + "def v(p, n):\n    return html(t'<p>{p:.2f} {n!r}</p>')\n")
    from wybthon.testing import render

    with render(ns["v"](2.5, "x")) as screen:
        assert screen.html() == "<p>2.50 'x'</p>"


def test_is_dynamic_ignores_lambda_bodies():
    assert compiler.is_dynamic(ast.parse("a.b", mode="eval").body)
    assert compiler.is_dynamic(ast.parse("f()", mode="eval").body)
    assert compiler.is_dynamic(ast.parse("x[0]", mode="eval").body)
    assert not compiler.is_dynamic(ast.parse("lambda: f()", mode="eval").body)
    assert not compiler.is_dynamic(ast.parse("a + b", mode="eval").body)


# ---------------------------------------------------------------------------
# Captured names
# ---------------------------------------------------------------------------


def _captures(expr: ast.expr) -> list[str]:
    assert isinstance(expr, ast.Lambda)
    return [arg.arg for arg in expr.args.kwonlyargs]


def test_zero_argument_calls_and_method_calls_are_plain_expressions():
    found = _interpolations(
        _tree(
            HEADER
            + """
def view(count, Footer, item, ui):
    return html(t'<p>{count()}{Footer()}{item.upper()}{ui.Card(title=count())}{ui.helper(1)}</p>')
"""
        )
    )
    assert _kind(found["count()"]) == "lambda"
    assert _kind(found["Footer()"]) == "lambda"
    assert _kind(found["item.upper()"]) == "lambda"
    assert _kind(found["ui.Card(title=count())"]) == "call"
    assert _kind(found["ui.helper(1)"]) == "lambda"


def test_names_bound_once_are_closures_and_loop_variables_are_captured():
    found = _interpolations(
        _tree(
            HEADER
            + """
def view(d, items):
    iid = d["id"]
    rows = []
    for item in items:
        rows.append(html(t'<li>{item.upper()}{d["label"]}{iid.bit_length()}</li>'))
    return [html(t'<b>{x.title()}</b>') for x in items]
"""
        )
    )
    assert _captures(found["item.upper()"]) == ["item"]
    assert _captures(found['d["label"]']) == []
    assert _captures(found["iid.bit_length()"]) == []
    assert _captures(found["x.title()"]) == ["x"]


def test_loop_templates_render_their_own_iteration():
    ns = _run(
        HEADER
        + """
def views(names):
    out = []
    for name in names:
        out.append(html(t'<li>{name.upper()}</li>'))
    return html(t'<ul>{out}</ul>')
"""
    )
    from wybthon.testing import render

    with render(ns["views"](["a", "b", "c"])) as screen:
        assert screen.html() == "<ul><li>A</li><li>B</li><li>C</li></ul>"


def test_reassigned_names_are_captured_at_template_time():
    ns = _run(
        HEADER
        + """
def view():
    label = "first"
    node = html(t'<p>{label.upper()}</p>')
    label = "second"
    return node
"""
    )
    from wybthon.testing import render

    with render(ns["view"]()) as screen:
        assert screen.html() == "<p>FIRST</p>"


def test_names_defined_after_the_template_resolve_when_the_getter_runs():
    ns = _run(
        HEADER
        + """
def view():
    node = html(t'<p>{config.label}</p>')

    class config:
        label = "late"

    return node
"""
    )
    from wybthon.testing import render

    with render(ns["view"]()) as screen:
        assert screen.html() == "<p>late</p>"


def test_class_body_templates_see_class_names():
    ns = _run(
        HEADER
        + """
class Holder:
    word = "class"
    view = html(t'<p>{word.upper()}</p>')
"""
    )
    from wybthon.testing import render

    with render(ns["Holder"].view) as screen:
        assert screen.html() == "<p>CLASS</p>"


# ---------------------------------------------------------------------------
# Behavior of compiled templates
# ---------------------------------------------------------------------------


def test_dynamic_expressions_update_in_place():
    ns = _run(
        HEADER
        + """
count, set_count = create_signal(1)
active, set_active = create_signal(False)

def view():
    return html(t'<p class={"on" if active() else "off"} data-n="n{count()}">{count() * 10}</p>')
"""
    )
    from wybthon.testing import render

    with render(ns["view"]()) as screen:
        assert screen.html() == '<p class="off" data-n="n1">10</p>'
        ns["set_count"](4)
        ns["set_active"](True)
        ns["flush"]()
        assert screen.html() == '<p class="on" data-n="n4">40</p>'


def test_component_tags_and_calls_receive_getters_without_rerunning():
    ns = _run(
        HEADER
        + """
runs = []
name, set_name = create_signal("ada")

class CardProps(Props):
    title: str

@component
def Card(props: CardProps):
    runs.append(1)
    return html(t'<h2>{props.title}</h2>')

def view():
    return html(t'<div><{Card} title={name().upper()} />{Card(title=name() + "!")}</div>')
"""
    )
    from wybthon.testing import render

    with render(ns["view"]()) as screen:
        assert screen.html() == "<div><h2>ADA</h2><h2>ada!</h2></div>"
        ns["set_name"]("grace")
        ns["flush"]()
        assert screen.html() == "<div><h2>GRACE</h2><h2>grace!</h2></div>"
        assert len(ns["runs"]) == 2


def test_plain_function_calls_are_reactive_holes():
    ns = _run(
        HEADER
        + """
from fractions import Fraction

n, set_n = create_signal(1)

def badge(value):
    return html(t'<b>{value}</b>') if value > 1 else "small"

def view():
    return html(t'<p>{badge(n())}|{Fraction(n(), 2)}</p>')
"""
    )
    from wybthon.testing import render

    with render(ns["view"]()) as screen:
        assert screen.html() == "<p>small|1/2</p>"
        ns["set_n"](4)
        ns["flush"]()
        assert screen.html() == "<p><b>4</b>|2</p>"


def test_flow_controls_called_in_templates_take_getters():
    ns = _run(
        HEADER
        + """
count, set_count = create_signal(0)
items, set_items = create_signal(["a"])

def row(item, index):
    return html(t'<li>{item}{index()}</li>')

def view():
    return html(t'<div>{Show(count() > 1, html(t"<i>many</i>"))}<ul>{For(items(), row)}</ul></div>')
"""
    )
    from wybthon.testing import render

    with render(ns["view"]()) as screen:
        assert screen.html() == "<div><ul><li>a0</li></ul></div>"
        ns["set_count"](2)
        ns["set_items"](["b", "a"])
        ns["flush"]()
        assert screen.html() == "<div><i>many</i><ul><li>b0</li><li>a1</li></ul></div>"


def test_format_specs_render_reactively():
    ns = _run(
        HEADER
        + """
price, set_price = create_signal(1.5)

def view():
    return html(t'<p>{price():.2f} {price()!r}</p>')
"""
    )
    from wybthon.testing import render

    with render(ns["view"]()) as screen:
        assert screen.html() == "<p>1.50 1.5</p>"
        ns["set_price"](2.25)
        ns["flush"]()
        assert screen.html() == "<p>2.25 2.25</p>"


# ---------------------------------------------------------------------------
# Resolving `html`
# ---------------------------------------------------------------------------


def test_aliases_and_the_package_attribute_resolve():
    aliased = _interpolations(
        _tree("from wybthon import html as markup\ndef v(n):\n    return markup(t'<p>{n()}</p>')\n")
    )
    assert _kind(aliased["n()"]) == "lambda"
    package = _interpolations(_tree("import wybthon as w\ndef v(n):\n    return w.html(t'<p>{n()}</p>')\n"))
    assert _kind(package["n()"]) == "lambda"
    submodule = _interpolations(
        _tree("from wybthon.templates import html\ndef v(n):\n    return html(t'<p>{n()}</p>')\n")
    )
    assert _kind(submodule["n()"]) == "lambda"


def test_modules_with_their_own_html_are_left_alone():
    source = "def html(t):\n    return t\ndef v(n):\n    return html(t'<p>{n()}</p>')\n"
    tree = compiler.transform(ast.parse(source), "m.py", source)
    assert ast.unparse(tree) == ast.unparse(ast.parse(source))
    assert not any(isinstance(node, ast.Import) for node in tree.body)


def test_template_errors_are_syntax_errors_with_their_location():
    source = HEADER + "\n\ndef v():\n    return html(t'<table><tr></tr></table>')\n"
    with pytest.raises(SyntaxError) as info:
        compiler.compile_source(source, "broken.py")
    assert info.value.filename == "broken.py"
    assert info.value.lineno == 6
    assert "tbody" in str(info.value)


# ---------------------------------------------------------------------------
# Precompiled entries
# ---------------------------------------------------------------------------


def test_each_literal_gets_a_precompiled_entry_and_mount_functions():
    ns = _run(HEADER + "def v(n):\n    return html(t'<p>{n()}</p>')\n")
    entry = ns["__wybthon_t0__"]
    assert isinstance(entry, templates.Precompiled)
    assert callable(ns["__wybthon_m0__"])
    before = len(templates._by_identity)
    from wybthon.testing import render

    with render(ns["v"](lambda: 3)) as screen:
        assert screen.html() == "<p>3</p>"
    assert entry.entry is not None
    assert len(templates._by_identity) == before


def test_probes_cover_deferred_expressions_without_calls():
    ns = _run(HEADER + "def v(props, count):\n    return html(t'<p title={props.title}>{count()}{props.body}</p>')\n")
    entry = ns["__wybthon_t0__"]
    assert entry.probes == frozenset({0, 2})


def test_component_tag_getters_mark_probes():
    ns = _run(HEADER + "def v(Card, user, count):\n    return html(t'<{Card} a={user.name} b={count()} />')\n")
    seen: list[Any] = []

    def Card(**props):
        seen.append(props)
        from wybthon import h

        return h("i", None)

    class User:
        name = "x"

    ns["v"](Card, User(), lambda: 1)
    props = seen[0]
    assert isinstance(props["a"], _Getter) and props["a"].probe
    assert isinstance(props["b"], _Getter) and not props["b"].probe


# ---------------------------------------------------------------------------
# The dev-mode check for templates that weren't compiled
# ---------------------------------------------------------------------------


def test_defers_matches_the_compiler():
    assert compiler.defers("count() * 2", "child")
    assert compiler.defers("props.title", "attr")
    assert compiler.defers("user().name", "prop")
    assert not compiler.defers("count", "child")
    assert not compiler.defers("make(1)", "event")
    assert not compiler.defers("attrs.copy()", "spread")
    assert not compiler.defers('html(t"<b>x</b>")', "child")
    assert not compiler.defers("Card(title='x')", "child")
    assert compiler.defers("Card(title=name())", "child")
    assert not compiler.defers("(lambda: x())", "child")


# ---------------------------------------------------------------------------
# The import hook
# ---------------------------------------------------------------------------


MODULE = (
    HEADER
    + """
def view(n):
    return html(t'<p>{n() + 1}</p>')
"""
)


@pytest.fixture()
def module_dir(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setattr(sys, "dont_write_bytecode", False)
    _hook.install()
    yield tmp_path
    for name in list(sys.modules):
        if name.startswith("hooked_"):
            del sys.modules[name]


def test_the_hook_compiles_candidates_and_caches_them(module_dir, monkeypatch):
    (module_dir / "hooked_a.py").write_text(MODULE, encoding="utf-8")
    module = importlib.import_module("hooked_a")
    assert isinstance(module.__wybthon_t0__, templates.Precompiled)
    cache = Path(importlib.util.cache_from_source(str(module_dir / "hooked_a.py"), optimization=_hook.COMPILER_TAG))
    assert cache.exists()
    del sys.modules["hooked_a"]

    def fail(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("the cached code should have been used")

    monkeypatch.setattr(compiler, "compile_source", fail)
    module = importlib.import_module("hooked_a")
    assert isinstance(module.__wybthon_t0__, templates.Precompiled)


def test_the_hook_leaves_other_modules_alone(module_dir):
    (module_dir / "hooked_plain.py").write_text("VALUE = 1\n", encoding="utf-8")
    module = importlib.import_module("hooked_plain")
    assert module.VALUE == 1
    assert not hasattr(module, "__wybthon__")


def test_the_hook_uses_built_bytecode_as_is(module_dir):
    path = module_dir / "hooked_built.py"
    path.write_text(MODULE, encoding="utf-8")
    from importlib._bootstrap_external import _code_to_hash_pyc

    built = compile("VALUE = 'built'\n", str(path), "exec")
    data = bytes(_code_to_hash_pyc(built, importlib.util.source_hash(path.read_bytes()), checked=False))
    pyc = Path(importlib.util.cache_from_source(str(path)))
    pyc.parent.mkdir(exist_ok=True)
    pyc.write_bytes(data)
    module = importlib.import_module("hooked_built")
    assert module.VALUE == "built"


def test_the_hook_skips_the_standard_library_and_wybthon():
    assert _hook._skipped(str(Path(templates.__file__)))
    assert _hook._skipped(str(Path(ast.__file__)))
    assert not _hook._skipped(str(Path(__file__)))


def test_install_is_idempotent_and_sits_before_the_path_finder():
    _hook.install()
    _hook.install()
    assert sys.meta_path.count(_hook._Finder) == 1
    from importlib.machinery import PathFinder

    assert sys.meta_path.index(_hook._Finder) < sys.meta_path.index(PathFinder)


def test_cached_code_is_rejected_when_the_source_changes(module_dir):
    path = module_dir / "hooked_stale.py"
    path.write_text(MODULE, encoding="utf-8")
    importlib.import_module("hooked_stale")
    cache = Path(importlib.util.cache_from_source(str(path), optimization=_hook.COMPILER_TAG))
    data = cache.read_bytes()
    code = marshal.loads(data[16:])
    assert code.co_filename == str(path)
    del sys.modules["hooked_stale"]
    path.write_text(MODULE + "EXTRA = 2\n", encoding="utf-8")
    module = importlib.import_module("hooked_stale")
    assert module.EXTRA == 2


# ---------------------------------------------------------------------------
# pytest and `wyb run`
# ---------------------------------------------------------------------------


def test_the_pytest_plugin_compiles_test_modules():
    from _pytest.assertion import rewrite

    import wybthon_pytest

    assert getattr(rewrite.rewrite_asserts, "_wybthon", False)
    assert wybthon_pytest.COMPILER_TAG == _hook.COMPILER_TAG
    assert _hook.COMPILER_TAG in rewrite.PYC_TAIL
    # This very module's templates were compiled by it.
    found = [value for name, value in globals().items() if name.startswith("__wybthon_t")]
    assert not found  # this module has no html() calls of its own


def test_wyb_run_compiles_the_script(tmp_path, monkeypatch):
    out = tmp_path / "out.txt"
    script = tmp_path / "script.py"
    script.write_text(
        HEADER
        + f"""
from wybthon.testing import render
n, set_n = create_signal(1)
with render(html(t'<p>{{n() * 3}}</p>')) as screen:
    set_n(2)
    flush()
    open({str(out)!r}, "w").write(screen.html())
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(sys, "argv", list(sys.argv))
    monkeypatch.setattr(sys, "path", list(sys.path))
    from wybthon.dev import run_script

    assert run_script(str(script), []) == 0
    assert out.read_text() == "<p>6</p>"


def test_a_getter_prop_that_returns_an_accessor_reads_its_value():
    ns = _run(
        HEADER
        + """
class Model:
    def __init__(self):
        self.title, self.set_title = create_signal("one")

    def shout(self):
        return self.title().upper()

class CardProps(Props):
    title: str

@component
def Card(props: CardProps):
    return html(t'<h2>{props.title}</h2>')

model = Model()

def view():
    return html(t'<div><{Card} title={model.title} /><{Card} title={model.shout} /></div>')
"""
    )
    from wybthon.testing import render

    with render(ns["view"]()) as screen:
        assert screen.html() == "<div><h2>one</h2><h2>ONE</h2></div>"
        ns["model"].set_title("two")
        ns["flush"]()
        assert screen.html() == "<div><h2>two</h2><h2>TWO</h2></div>"


def test_flow_controls_read_through_getters_that_return_accessors():
    ns = _run(
        HEADER
        + """
from wybthon import Accessor

class ListProps(Props):
    items: Accessor[list[str]]
    flag: Accessor[bool]

@component
def Items(props: ListProps):
    def row(item, i):
        return html(t"<li>{item}</li>")

    return html(t'<ul>{Show(props.flag, html(t"<b>on</b>"))}{For(props.items, row)}</ul>')

items, set_items = create_signal(["a"])
flag, set_flag = create_signal(False)

def view():
    return html(t'<{Items} items={items} flag={flag} />')
"""
    )
    from wybthon.testing import render

    with render(ns["view"]()) as screen:
        assert screen.html() == "<ul><li>a</li></ul>"
        ns["set_items"](["a", "b"])
        ns["set_flag"](True)
        ns["flush"]()
        assert screen.html() == "<ul><b>on</b><li>a</li><li>b</li></ul>"
