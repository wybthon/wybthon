import importlib.metadata
import json
import socketserver
from io import BytesIO
from pathlib import Path

import pytest

import wybthon.dev as dev
from wybthon.build import init_app
from wybthon.dev import SSEHandler, _walk_files, main, serve


class _Sink:
    def __init__(self, should_fail: bool = False) -> None:
        self.buf = BytesIO()
        self.should_fail = should_fail
        self.closed = False

    def write(self, b: bytes) -> int:
        if self.should_fail:
            raise OSError("broken pipe")
        return self.buf.write(b)

    def flush(self) -> None:
        if self.should_fail:
            raise OSError("broken pipe")


def _handler(root: Path, base: str = "/") -> SSEHandler:
    """An `SSEHandler` without a socket, for exercising `translate_path`."""
    handler = SSEHandler.__new__(SSEHandler)
    handler.root = root
    handler.app_base = base
    return handler


def test_walk_files_collects_files(tmp_path: Path):
    d = tmp_path / "a"
    d.mkdir()
    f1 = d / "f1.txt"
    f1.write_text("one")
    f2 = tmp_path / "f2.txt"
    f2.write_text("two")

    got = sorted(str(p) for p in _walk_files([tmp_path, tmp_path / "missing"]))
    assert str(f1) in got and str(f2) in got
    assert len(got) == 2


def test_sse_notify_removes_dead_watchers():
    original = list(SSEHandler.watchers)
    try:
        ok = _Sink()
        bad = _Sink(should_fail=True)
        SSEHandler.watchers = [ok, bad]
        SSEHandler.notify_reload()
        # The dead watcher is removed.
        assert ok in SSEHandler.watchers
        assert bad not in SSEHandler.watchers
        # The payload follows the SSE protocol.
        data = ok.buf.getvalue().decode("utf-8")
        assert "event: reload" in data and "data: {}" in data
    finally:
        SSEHandler.watchers = original


def test_translate_path_serves_build_files(tmp_path: Path):
    (tmp_path / "index.html").write_text("ok")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.js").write_text("js")
    handler = _handler(tmp_path)
    assert Path(handler.translate_path("/index.html")) == tmp_path / "index.html"
    assert Path(handler.translate_path("/")) == tmp_path / "index.html"
    assert Path(handler.translate_path("/assets/app.js?v=1#x")) == tmp_path / "assets" / "app.js"


def test_translate_path_sanitizes_traversal(tmp_path: Path):
    (tmp_path / "safe.txt").write_text("ok")
    handler = _handler(tmp_path)
    assert Path(handler.translate_path("/../safe.txt?x=1#y")) == tmp_path / "safe.txt"
    resolved = Path(handler.translate_path("/../../etc/passwd"))
    assert resolved.is_relative_to(tmp_path)


def test_translate_path_client_routes_fall_back_to_shell(tmp_path: Path):
    (tmp_path / "200.html").write_text("shell")
    handler = _handler(tmp_path)
    assert Path(handler.translate_path("/users/42")) == tmp_path / "200.html"
    # Missing files with an extension stay missing (a real 404).
    assert Path(handler.translate_path("/missing.js")) == tmp_path / "missing.js"


def test_translate_path_honors_app_base(tmp_path: Path):
    (tmp_path / "index.html").write_text("ok")
    (tmp_path / "200.html").write_text("shell")
    handler = _handler(tmp_path, base="/demo/")
    assert Path(handler.translate_path("/demo/")) == tmp_path / "index.html"
    assert Path(handler.translate_path("/demo")) == tmp_path / "index.html"
    assert Path(handler.translate_path("/demo/route")) == tmp_path / "200.html"
    # Paths outside the base are never served.
    assert Path(handler.translate_path("/other/index.html")) == tmp_path / "__missing__"
    assert Path(handler.translate_path("/democracy")) == tmp_path / "__missing__"


def test_static_mode_helpers_are_gone():
    for name in ("translate_request_path", "parse_mounts"):
        assert not hasattr(dev, name)
    assert dev.__all__ == ["serve", "main"]


def test_serve_requires_a_project(tmp_path: Path):
    (tmp_path / "index.html").write_text("<p>plain directory</p>")
    with pytest.raises(ValueError, match="wybthon.toml"):
        serve(tmp_path)


def test_dev_command_rejects_non_project_and_removed_flags(tmp_path: Path, capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(["dev", "--dir", str(tmp_path)])
    assert excinfo.value.code == 2
    assert "wybthon.toml" in capsys.readouterr().err
    for flags in (["--mount", "/x=."], ["--watch", "."]):
        with pytest.raises(SystemExit) as excinfo:
            main(["dev", "--dir", str(tmp_path), *flags])
        assert excinfo.value.code == 2
        capsys.readouterr()


def test_serve_builds_in_dev_mode_with_reload_script(tmp_path: Path, monkeypatch, capsys):
    project = tmp_path / "project"
    init_app(project)
    started: list[object] = []

    class NoThread:
        def __init__(self, target, daemon=False):
            started.append(target)

        def start(self) -> None:
            pass

    def stop(self, *args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(dev.threading, "Thread", NoThread)
    monkeypatch.setattr(socketserver.BaseServer, "serve_forever", stop)
    root, base = SSEHandler.root, SSEHandler.app_base
    try:
        serve(project, port=0)
        assert SSEHandler.root == project / "dist"
        assert SSEHandler.app_base == "/"
    finally:
        SSEHandler.root, SSEHandler.app_base = root, base
    manifest = json.loads((project / "dist" / "manifest.json").read_text())
    assert manifest["dev"] is True
    for page in ("index.html", "200.html"):
        assert "/__sse" in (project / "dist" / page).read_text()
    assert len(started) == 1  # the file watcher
    assert "Serving at: http://127.0.0.1:" in capsys.readouterr().out


def test_build_command_writes_production_manifest(tmp_path: Path, capsys):
    project = tmp_path / "project"
    assert main(["init", str(project)]) == 0
    assert main(["build", "--dir", str(project), "--base", "/demo/"]) == 0
    manifest = json.loads((project / "dist" / "manifest.json").read_text())
    assert manifest["dev"] is False
    assert manifest["base"] == "/demo/"
    assert "/__sse" not in (project / "dist" / "index.html").read_text()
    assert "Built" in capsys.readouterr().out


def test_no_command_prints_help(capsys):
    assert main([]) == 1
    assert "usage: wyb" in capsys.readouterr().out


def test_version_flag_prints_package_version_and_exits(capsys):
    expected = importlib.metadata.version("wybthon")
    for flag in ("--version", "-V"):
        with pytest.raises(SystemExit) as excinfo:
            main([flag])
        assert excinfo.value.code == 0
        assert capsys.readouterr().out.strip() == f"wyb {expected}"
