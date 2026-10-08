"""SolidJS 2.0 RC parity sweep, list clearing, and the prerendering build (RFC 0001)."""

from __future__ import annotations

import importlib
import json
import sys
import zipfile

import pytest
from conftest import collect_texts

from wybthon import (
    For,
    Show,
    WriteInScopeError,
    create_memo,
    create_owner,
    create_signal,
    diagnostics,
    div,
    flush,
    is_disposed,
    li,
    p,
    run_with_owner,
    ul,
)
from wybthon.build import build_app, init_app
from wybthon.kernel import OP_DISPOSE_RANGE

# ---------------------------------------------------------------------------
# Reactive API
# ---------------------------------------------------------------------------


def test_flush_with_a_function_applies_its_writes(wyb):
    count, set_count = create_signal(0)
    result = flush(lambda: set_count(5))
    assert result == 5
    assert count() == 5
    assert flush() is None


def test_owned_write_is_exempt_from_the_scope_guard(wyb):
    source, set_source = create_signal(1)
    cache, set_cache = create_signal(0, owned_write=True)
    guarded, set_guarded = create_signal(0)

    def derive() -> int:
        value = source() * 2
        set_cache(value)
        return value

    doubled = create_memo(derive)
    assert doubled() == 2
    flush()
    assert cache() == 2
    failing = create_memo(lambda: set_guarded(source()))
    with pytest.raises(WriteInScopeError):
        failing()


def test_create_owner_and_is_disposed(wyb):
    parent = create_owner()
    child = run_with_owner(parent, create_owner)
    assert not is_disposed(child)
    parent.dispose()
    assert is_disposed(parent) and is_disposed(child)


def test_top_level_reads_in_control_flow_callbacks_warn(wyb, root_element, capsys):
    items, _ = create_signal([1])
    flag, _ = create_signal(True)

    def row(item, index):
        index()
        return li(str(item))

    def branch(value):
        value()
        return p("yes")

    wyb["reconciler"].render(div(ul(For(items, row)), Show(flag, branch)), root_element)
    err = capsys.readouterr().err
    assert "A For callback read reactive value" in err
    assert "A Show or Match callback read reactive value" in err


def test_reads_inside_holes_in_callbacks_do_not_warn(wyb, root_element, capsys):
    items, _ = create_signal([1, 2])
    wyb["reconciler"].render(ul(For(items, lambda item, index: li(lambda: f"{index()}: {item}"))), root_element)
    assert "callback read reactive value" not in capsys.readouterr().err
    assert [t for t in collect_texts(root_element.element) if t] == ["0: 1", "1: 2"]


# ---------------------------------------------------------------------------
# Clearing lists
# ---------------------------------------------------------------------------


def test_clearing_a_list_emits_one_range_removal(wyb, root_element):
    items, set_items = create_signal(list(range(50)))
    cleanups: list[int] = []

    def row(item, index):
        from wybthon import on_cleanup

        on_cleanup(lambda: cleanups.append(item))
        return li(str(item))

    wyb["reconciler"].render(ul(For(items, row)), root_element)
    with diagnostics.profile() as measured:
        set_items([])
        flush()
    counts = measured.as_dict()
    assert counts.get(f"op_{OP_DISPOSE_RANGE}") == 1
    assert sorted(cleanups) == list(range(50))
    assert [t for t in collect_texts(root_element.element) if t] == []
    set_items([7])
    flush()
    assert [t for t in collect_texts(root_element.element) if t] == ["7"]


def test_clearing_a_store_list_keeps_reverse_cleanup_order(wyb, root_element):
    from wybthon import create_store, on_cleanup

    store, set_store = create_store({"items": [1, 2, 3]})
    order: list[int] = []

    def row(item, index):
        on_cleanup(lambda: order.append(item))
        return li(str(item))

    wyb["reconciler"].render(ul(For(lambda: store["items"], row)), root_element)
    set_store(lambda draft: draft["items"].clear())
    flush()
    assert order == [3, 2, 1]
    assert [t for t in collect_texts(root_element.element) if t] == []


# ---------------------------------------------------------------------------
# Build: prerendering and bytecode
# ---------------------------------------------------------------------------


def _write_app(project, body: str) -> None:
    (project / "app" / "main.py").write_text(body)


ROUTED_APP = """
from wybthon import component, create_memo, div, p
from wybthon.router import Link, Route, RouteProps, Router


@component
def Home():
    return div(p("home page"), Link("About", href="/about"), Link("Docs", href="/docs/intro"))


@component
def About():
    return p("about page")


@component
def Docs(props: RouteProps):
    page = create_memo(lambda: props.params()["page"])
    return p(t"docs {page}")


def app():
    return Router([Route("/", Home), Route("/about", About), Route("/docs/:page", Docs)])
"""


def test_build_prerenders_routes_and_crawls_links(tmp_path):
    project = tmp_path / "project"
    init_app(project)
    _write_app(project, ROUTED_APP)
    manifest = build_app(project)
    dist = project / "dist"
    assert manifest["prerendered"] == ["/", "/about", "/docs/intro"]
    home = (dist / "index.html").read_text()
    assert "home page" in home and "data-wyb-state" in home and "Loading..." not in home
    assert "about page" in (dist / "about" / "index.html").read_text()
    assert "docs intro" in (dist / "docs" / "intro" / "index.html").read_text()
    shell = (dist / "200.html").read_text()
    assert "Loading..." in shell and "data-wyb-state" not in shell


def test_build_reports_prerender_failures(tmp_path):
    project = tmp_path / "project"
    init_app(project)
    _write_app(project, "import js\n\ndef app():\n    return None\n")
    with pytest.raises(ValueError, match="is_server"):
        build_app(project)


def test_build_without_prerendering_keeps_the_shell(tmp_path):
    project = tmp_path / "project"
    init_app(project)
    config = project / "wybthon.toml"
    config.write_text(config.read_text().replace('prerender = ["/"]', "prerender = []"))
    manifest = build_app(project)
    assert manifest["prerendered"] == []
    assert "Loading..." in (project / "dist" / "index.html").read_text()


def test_build_validates_prerender_configuration(tmp_path):
    project = tmp_path / "project"
    init_app(project)
    config = project / "wybthon.toml"
    config.write_text(config.read_text().replace('prerender = ["/"]', 'prerender = ["about"]'))
    with pytest.raises(ValueError, match="prerender"):
        build_app(project)
    config.write_text(config.read_text().replace('prerender = ["about"]', 'prerender = ["/"]'))
    (project / "index.html").write_text("<html><body><div id=app></div><!-- wyb:bootstrap --></body></html>")
    with pytest.raises(ValueError, match="wyb:app"):
        build_app(project)


def test_build_ships_bytecode_when_the_runtime_matches(tmp_path, monkeypatch):
    import wybthon.build as build

    monkeypatch.setattr(build, "_pyodide_python", lambda version: sys.version_info[:2])
    project = tmp_path / "project"
    init_app(project)
    manifest = build_app(project)
    assert manifest["bytecode"] is True
    tag = sys.implementation.cache_tag
    with zipfile.ZipFile(project / "dist" / manifest["runtime"]) as archive:
        names = archive.namelist()
        assert f"wybthon/__pycache__/reconciler.{tag}.pyc" in names
        assert not any(name.startswith("wybthon/server") for name in names)
    with zipfile.ZipFile(project / "dist" / manifest["application"]) as archive:
        assert f"app/__pycache__/main.{tag}.pyc" in archive.namelist()
        archive.extractall(tmp_path / "unpacked")
    # The bytecode imports without consulting the source.
    (tmp_path / "unpacked" / "app" / "main.py").write_text("raise RuntimeError('source was compiled')\n")
    sys.path.insert(0, str(tmp_path / "unpacked"))
    try:
        sys.modules.pop("app.main", None)
        sys.modules.pop("app", None)
        module = importlib.import_module("app.main")
        assert callable(module.app)
    finally:
        sys.path.remove(str(tmp_path / "unpacked"))
        sys.modules.pop("app.main", None)
        sys.modules.pop("app", None)


def test_pyodide_python_versions():
    from wybthon.build import _pyodide_python

    assert _pyodide_python("314.0.6") == (3, 14)
    assert _pyodide_python("0.27.7") == (3, 12)
    assert _pyodide_python("9.9.9") is None


def test_manifest_records_mount(tmp_path):
    project = tmp_path / "project"
    init_app(project)
    manifest = build_app(project)
    assert manifest["mount"] == "#app"
    assert json.loads((project / "dist" / "manifest.json").read_text())["entry"] == "app.main:app"
