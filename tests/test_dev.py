from io import BytesIO
from pathlib import Path

from wybthon.dev import SSEHandler, _walk_files


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
