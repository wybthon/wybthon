import importlib

import pytest

try:
    importlib.import_module("js")
    HAS_JS = True
except Exception:
    HAS_JS = False


@pytest.mark.skipif(not HAS_JS, reason="requires Pyodide/js module")
def test_load_component_imports(monkeypatch):
    # Ensure we can import the lazy module and call load_component without error
    wyb = importlib.import_module("wybthon")
    load_component = getattr(wyb, "load_component")

    # Use an existing demo module that defines Page(props)
    # The demo modules are importable when tests run in repo root with PYTHONPATH including examples
    comp = load_component("examples.demo.app.about.page", "Page")

    # Calling the returned factory should yield a VNode-like; we can at least call it
    vnode = comp({})
    assert vnode is not None


@pytest.mark.skipif(not HAS_JS, reason="requires Pyodide/js module")
def test_preload_component_no_throw():
    wyb = importlib.import_module("wybthon")
    preload = getattr(wyb, "preload_component")
    # Should not raise even if module is already loaded
    preload("examples.demo.app.about.page", "Page")
