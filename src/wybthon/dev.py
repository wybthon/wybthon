from __future__ import annotations

import argparse
import http.server
import io
import json
import os
import socketserver
import sys
import threading
import time
from pathlib import Path
from typing import Iterable


class SSEHandler(http.server.SimpleHTTPRequestHandler):
    watchers = []  # type: ignore[var-annotated]
    root: Path = Path.cwd()

    def do_GET(self):  # noqa: N802
        if self.path == "/__sse":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            # Register this client
            self.watchers.append(self.wfile)
            try:
                # Keep open until client disconnects
                while True:
                    time.sleep(1)
            except Exception:
                pass
            finally:
                try:
                    self.watchers.remove(self.wfile)
                except Exception:
                    pass
            return
        return super().do_GET()

    @classmethod
    def notify_reload(cls) -> None:
        dead: list = []
        for w in list(cls.watchers):
            try:
                w.write(b"event: reload\n")
                w.write(b"data: {}\n\n")
                w.flush()
            except Exception:
                dead.append(w)
        for d in dead:
            try:
                cls.watchers.remove(d)
            except Exception:
                pass


def _walk_files(paths: Iterable[Path]) -> Iterable[Path]:
    for p in paths:
        if p.is_dir():
            for root, _dirs, files in os.walk(p):
                for f in files:
                    yield Path(root) / f
        elif p.exists():
            yield p


def serve(directory: str, host: str = "127.0.0.1", port: int = 8000, watch: Iterable[str] = ("src", "examples")) -> None:
    os.chdir(directory)
    SSEHandler.root = Path(directory)
    handler_cls = SSEHandler

    class ReuseTCPServer(socketserver.TCPServer):
        allow_reuse_address = True

    def watcher() -> None:
        mtimes: dict[Path, float] = {}
        roots = [Path(w) for w in watch]
        while True:
            changed = False
            for f in _walk_files(roots):
                try:
                    m = f.stat().st_mtime
                except Exception:
                    continue
                prev = mtimes.get(f)
                if prev is None:
                    mtimes[f] = m
                elif m > prev:
                    mtimes[f] = m
                    changed = True
            if changed:
                handler_cls.notify_reload()
            time.sleep(0.5)

    t = threading.Thread(target=watcher, daemon=True)
    t.start()

    # Try to bind desired port; if busy, fall back to next available up to +20
    candidates = [port] if port and port > 0 else [0]
    if port and port > 0:
        candidates += list(range(port + 1, port + 21))

    httpd = None
    bound_port = None
    last_err = None
    for p in candidates:
        try:
            httpd = ReuseTCPServer((host, p), handler_cls)
            bound_port = httpd.server_address[1]
            break
        except OSError as e:
            last_err = e
            continue
    if httpd is None:
        raise last_err if last_err is not None else OSError("Failed to bind server")

    print(f"Serving {directory} at http://{host}:{bound_port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            httpd.server_close()
        except Exception:
            pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="wyb", description="Wybthon dev server")
    sub = parser.add_subparsers(dest="cmd")
    pdev = sub.add_parser("dev", help="Start dev server with auto-reload")
    pdev.add_argument("--dir", default=str(Path(__file__).resolve().parents[2]), help="Root dir to serve")
    pdev.add_argument("--host", default="127.0.0.1")
    pdev.add_argument("--port", type=int, default=8000)
    pdev.add_argument("--watch", nargs="*", default=["src", "examples"]) 

    args = parser.parse_args(argv)
    if args.cmd == "dev":
        serve(args.dir, host=args.host, port=args.port, watch=args.watch)
        return 0
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
