"""Boot snapshots (RFC 0006): the manifest key, what a snapshot preloads, and the bootstrap's use of it."""

import zipfile
from pathlib import Path

import pytest

from wybthon import _snapshot
from wybthon.build import build_app, init_app


def _project(tmp_path: Path) -> Path:
    app = tmp_path / "project"
    init_app(app)
    return app


def test_builds_key_a_snapshot_by_the_runtime_not_the_application(tmp_path: Path):
    app = _project(tmp_path)
    first = build_app(app)
    assert isinstance(first["snapshot"], str) and len(first["snapshot"]) == 20
    # Application changes keep the key: a snapshot holds only the framework,
    # so every `wyb dev` rebuild restores the same one.
    main = app / "app" / "main.py"
    main.write_text(main.read_text().replace("My Wybthon app", "Changed"))
    second = build_app(app)
    assert second["application"] != first["application"]
    assert second["snapshot"] == first["snapshot"]
    assert build_app(app, dev=True)["snapshot"] == first["snapshot"]
    # A different Pyodide release is a different runtime.
    config = app / "wybthon.toml"
    config.write_text(config.read_text().replace('pyodide-version = "314.0.6"', 'pyodide-version = "314.0.7"'))
    assert build_app(app)["snapshot"] != first["snapshot"]


@pytest.mark.parametrize(
    ("line", "replacement"),
    [
        ("packages = []", "packages = []\nsnapshot = false"),
        ("packages = []", 'packages = ["numpy"]'),
        ("wheels = []", 'wheels = ["attrs==25.1.0"]'),
    ],
)
def test_builds_without_a_snapshot_boot_normally(tmp_path: Path, line: str, replacement: str):
    # Packages and wheels live in the virtual file system, which a memory
    # snapshot doesn't hold.
    app = _project(tmp_path)
    config = app / "wybthon.toml"
    config.write_text(config.read_text().replace(line, replacement))
    assert build_app(app)["snapshot"] is None


def test_the_snapshot_setting_must_be_a_bool(tmp_path: Path):
    app = _project(tmp_path)
    config = app / "wybthon.toml"
    config.write_text('snapshot = "yes"\n' + config.read_text())
    with pytest.raises(ValueError, match="snapshot must be true or false"):
        build_app(app)


def test_the_runtime_ships_the_snapshot_preloader_but_not_the_server(tmp_path: Path):
    app = _project(tmp_path)
    manifest = build_app(app)
    with zipfile.ZipFile(app / "dist" / manifest["runtime"]) as archive:
        names = set(archive.namelist())
    assert "wybthon/_snapshot.py" in names
    assert "wybthon/_ssr.py" not in names and "wybthon/server.py" not in names


def test_preload_imports_the_framework_without_touching_the_page():
    import sys

    assert _snapshot.preload() == []
    for name in _snapshot.MODULES:
        assert name in sys.modules


def test_the_bootstrap_restores_and_builds_snapshots():
    source = (Path(__file__).parent.parent / "src" / "wybthon" / "_bootstrap.js").read_text()
    # Restores a cached snapshot, falls back to a normal boot when it can't,
    # and builds one in a worker only after a boot that didn't use one.
    assert "_loadSnapshot: saved" in source
    assert "forgetSnapshot(config)" in source
    assert "if (config.snapshot && !state.timings.snapshot) buildSnapshot(config, runtimeURL);" in source
    assert "_makeSnapshot: true" in source and "wybthon._snapshot.preload()" in source
    # Each app has its own cache, and a failed build isn't retried on every visit.
    assert '`wybthon-snapshot ${config.base || "/"}`' in source
    assert "snapshotFailedRecently(config)) return;" in source and "recordSnapshotFailure(config)" in source


def test_the_router_reads_the_page_on_first_use_not_at_import(monkeypatch: pytest.MonkeyPatch):
    # A snapshot imports the router in a worker with no `window`; a restored
    # page must read its own URL and install its own back/forward listener.
    import importlib
    import sys
    import types

    accessed: list[str] = []

    class Location:
        pathname = "/users/7"
        search = "?tab=a"
        hash = ""

    class Window:
        location = Location()

        def addEventListener(self, kind: str, _listener: object) -> None:
            accessed.append(kind)

    js = types.ModuleType("js")
    js.window = Window()  # type: ignore[attr-defined]
    ffi = types.ModuleType("pyodide.ffi")
    ffi.create_proxy = lambda fn: fn  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "js", js)
    monkeypatch.setitem(sys.modules, "pyodide", types.ModuleType("pyodide"))
    monkeypatch.setitem(sys.modules, "pyodide.ffi", ffi)
    router = importlib.reload(importlib.import_module("wybthon.router"))
    try:
        assert accessed == [] and router._located is False
        assert router.current_path() == "/users/7?tab=a"
        assert accessed == ["popstate", "hashchange"]
        router.current_path()
        assert accessed == ["popstate", "hashchange"]
    finally:
        monkeypatch.undo()
        importlib.reload(router)
