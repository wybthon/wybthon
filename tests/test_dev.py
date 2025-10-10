from io import BytesIO
from pathlib import Path

from wybthon.dev import (
    SSEHandler,
    _walk_files,
    parse_mounts,
    translate_request_path,
)


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


def test_walk_files_collects_files(tmp_path: Path):
    d = tmp_path / "a"
    d.mkdir()
    f1 = d / "f1.txt"
    f1.write_text("one")
    f2 = tmp_path / "f2.txt"
    f2.write_text("two")

    got = sorted(str(p) for p in _walk_files([tmp_path]))
    assert str(f1) in got and str(f2) in got


def test_sse_notify_removes_dead_watchers():
    # Snapshot and restore the original list
    original = list(SSEHandler.watchers)
    try:
        ok = _Sink()
        bad = _Sink(should_fail=True)
        SSEHandler.watchers = [ok, bad]
        SSEHandler.notify_reload()
        # Dead watcher should be removed
        assert ok in SSEHandler.watchers
        assert bad not in SSEHandler.watchers
        # Verify content format per SSE protocol
        data = ok.buf.getvalue().decode("utf-8")
        assert "event: reload" in data and "data: {}" in data
    finally:
        SSEHandler.watchers = original


def test_translate_request_path_root(tmp_path: Path):
    root = tmp_path
    (root / "index.html").write_text("ok")
    p = translate_request_path("/index.html", root, [])
    assert p == root / "index.html"


def test_translate_request_path_mounts_longest_prefix(tmp_path: Path):
    root = tmp_path / "root"
    a = tmp_path / "a"
    b = tmp_path / "a_long"
    root.mkdir()
    a.mkdir()
    b.mkdir()
    (a / "f.txt").write_text("A")
    (b / "f.txt").write_text("B")
    mounts = [("/a", a), ("/a/long", b)]
    # Longest prefix should win
    p = translate_request_path("/a/long/f.txt", root, mounts)
    assert p == b / "f.txt"
    # Shorter mount applies when path matches it but not the longer one
    p2 = translate_request_path("/a/f.txt", root, mounts)
    assert p2 == a / "f.txt"


def test_translate_request_path_sanitizes(tmp_path: Path):
    root = tmp_path
    (root / "safe.txt").write_text("ok")
    p = translate_request_path("/../safe.txt?x=1#y", root, [])
    # traversal is dropped, so it maps to /safe.txt under root
    assert p == root / "safe.txt"


def test_parse_mounts_relative_and_absolute(tmp_path: Path):
    base = tmp_path
    (base / "public").mkdir()
    m = parse_mounts(["/=/etc", "/static=public", "assets=public"], base)
    # Ensure leading slash added and relative path resolved
    assert ("/static", (base / "public").resolve()) in m
    assert ("/assets", (base / "public").resolve()) in m
